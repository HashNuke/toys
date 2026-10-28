"""Run Wi-Fi diagnostics over USB; the laptop keeps its own network connection."""
import argparse
import base64
import getpass
import json
import secrets
import time
from pathlib import Path
import serial
from board_runtime.serial_wifi import wifi_line

def record(line):
    if not line.startswith('DIAG '): return None
    try: return json.loads(line[5:])
    except json.JSONDecodeError: return None

class Diagnostics:
    def __init__(self, port='/dev/cu.usbserial-01CDD34C', log=None):
        self.port = serial.Serial(port=None, baudrate=115200, timeout=1, write_timeout=15, exclusive=True)
        self.port.dtr = self.port.rts = False
        self.port.port = port
        self.port.open()
        self.log = log
        time.sleep(2)
        self.port.write(b'HN:PING\n')
        self.wait(lambda line: line.startswith('HN:PONG'), 90)
    def read(self):
        line = self.port.readline().decode(errors='replace').strip()
        if line and self.log:
            self.log.write(json.dumps({'host_time': time.time(), 'line': line})+'\n')
            self.log.flush()
        return line
    def wait(self, predicate, timeout):
        end = time.monotonic()+timeout
        lines = []
        while time.monotonic()<end:
            line = self.read()
            if line: lines.append(line)
            if predicate(line): return lines
        raise TimeoutError('Board response timed out')
    def command(self, cmd, timeout=90):
        self.port.write((cmd+'\n').encode())
        def complete(line):
            value = record(line)
            if not value: return False
            expected = 'DIAG:REQUEST' if cmd.startswith('DIAG:REQUEST ') else cmd
            return value.get('type')=='done' and value.get('command')==expected
        return [r for line in self.wait(complete, timeout) if (r := record(line))]
    def wifi(self, ssid, password):
        request_id = secrets.token_hex(8)
        self.port.write(wifi_line(ssid,password,request_id))
        lines = self.wait(lambda line: line.startswith('BOARD:RESULT ') and json.loads(line[13:]).get('request_id')==request_id,90)
        result = json.loads(lines[-1][13:])
        if result['result']!='ok': raise RuntimeError(result)
        return result
    def idle(self, seconds):
        end = time.monotonic()+seconds
        while time.monotonic()<end: self.read()
    def request(self, url, method='GET', headers=None, body=''):
        payload=json.dumps({'url':url,'method':method,'headers':headers or {},'body':body}, separators=(',',':'))
        cmd='DIAG:REQUEST '+payload
        if len(cmd.encode())>512: raise ValueError('Request exceeds serial command limit')
        results=self.command(cmd)
        content=b''.join(base64.b64decode(r['base64']) for r in results if r.get('type')=='body')
        return results,content
    def close(self): self.port.close()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=['status','probe','scan','fetch','monitor','idle','wifi'])
    p.add_argument('value', nargs='?')
    p.add_argument('--port',default='/dev/cu.usbserial-01CDD34C')
    p.add_argument('--log',type=Path)
    p.add_argument('--output',type=Path,help='Save fetched body')
    args=p.parse_args()
    log=args.log.open('a') if args.log else None
    client=Diagnostics(args.port,log)
    try:
        if args.command=='wifi': print(json.dumps(client.wifi(args.value or input('SSID: '),getpass.getpass('Wi-Fi password: ')),indent=2))
        elif args.command=='idle': client.idle(float(args.value or 120))
        else:
            cmd='DIAG:'+args.command.upper()+((' '+args.value) if args.value else '')
            results=client.command(cmd)
            body=bytearray()
            for r in results:
                if r['type']=='body': body.extend(base64.b64decode(r['base64']))
                else: print(json.dumps(r))
            if args.output: args.output.write_bytes(body)
            elif body: print(body.decode(errors='replace'))
    finally:
        client.close()
        if log: log.close()
if __name__=='__main__': main()
