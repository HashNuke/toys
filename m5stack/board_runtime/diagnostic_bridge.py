"""Local RPC bridge to one persistent USB diagnostics connection.

Binds 127.0.0.1 only, requires a random bearer token stored in a private file.
No laptop Wi-Fi or routing changes. Firmware update requires stopping the bridge.
"""
import argparse
import base64
from http.server import HTTPServer,BaseHTTPRequestHandler
import json
import secrets
import time
import queue
import threading
from pathlib import Path
from board_runtime.diagnostics import Diagnostics
from board_runtime.serial_wifi import wifi_line

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--port',default='/dev/cu.usbserial-01CDD34C')
 p.add_argument('--listen',type=int,default=8766)
 p.add_argument('--directory',type=Path,default=Path(__file__).resolve().parents[2] / '.devices/diagnostics')
 args=p.parse_args(); args.directory.mkdir(parents=True,exist_ok=True)
 token=secrets.token_hex(32); tokenfile=args.directory/'bridge.token'; tokenfile.write_text(token); tokenfile.chmod(0o600)
 logfile=args.directory/'bridge.jsonl'; logfile.touch(mode=0o600)
 log=logfile.open('a'); client=Diagnostics(args.port,log)
 # Drain serial continuously: leaving status messages unread can fill the macOS
 # USB buffer and splice/truncate later responses.
 lines=queue.Queue(maxsize=4096); original_read=client.read; stopping=threading.Event()
 def reader():
  while not stopping.is_set():
   line=original_read()
   if line:
    try: lines.put_nowait(line)
    except queue.Full:
     lines.get_nowait(); lines.put_nowait(line)
 def queued_read():
  try: return lines.get(timeout=1)
  except queue.Empty: return ''
 client.read=queued_read
 threading.Thread(target=reader,daemon=True).start()
 class Handler(BaseHTTPRequestHandler):
  def log_message(self,*args): pass
  def do_POST(self):
   if self.headers.get('Authorization')!='Bearer '+token: self.send_error(403); return
   size=int(self.headers.get('Content-Length',0))
   if size>16384: self.send_error(413); return
   try:
    req=json.loads(self.rfile.read(size)); action=req.get('action','command')
    if action=='wifi':
     rid=secrets.token_hex(8); client.port.write(wifi_line(req['ssid'],req['password'],rid))
     deadline=time.monotonic()+90; next_status=0; result=None; samples=[]
     while time.monotonic()<deadline:
      if time.monotonic()>next_status: client.port.write(b'DIAG:STATUS\n'); next_status=time.monotonic()+3
      line=client.read()
      if line.startswith('DIAG '):
       try: samples.append(json.loads(line[5:]))
       except json.JSONDecodeError: pass
      if line.startswith('BOARD:RESULT '):
       value=json.loads(line[13:])
       if value.get('request_id')==rid: result=value; break
     if result is None: raise TimeoutError('Wi-Fi configuration timed out')
     response={'result':result,'samples':samples}
    elif action=='http':
     records,body=client.request(req['url'],req.get('method','GET'),req.get('headers'),req.get('body',''))
     response={'records':[r for r in records if r.get('type')!='body'],'base64':base64.b64encode(body).decode()}
    elif action=='idle': client.idle(min(float(req.get('seconds',30)),600)); response={'idle':True}
    else: response={'records':client.command(req['command'])}
    encoded=json.dumps(response).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
   except Exception as e:
    encoded=json.dumps({'error':str(e)}).encode(); self.send_response(500); self.send_header('Content-Length',str(len(encoded))); self.end_headers(); self.wfile.write(encoded)
 server=HTTPServer(('127.0.0.1',args.listen),Handler)
 print('Serial diagnostics bridge ready on 127.0.0.1:'+str(args.listen),flush=True)
 try: server.serve_forever()
 finally: server.server_close(); stopping.set(); client.close(); log.close(); tokenfile.unlink(missing_ok=True)
if __name__=='__main__': main()
