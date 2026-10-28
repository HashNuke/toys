import base64
import io
import json
from board_runtime.diagnostics import Diagnostics

class Port:
    def __init__(self, lines): self.lines=iter(lines); self.written=[]
    def readline(self): return (next(self.lines)+'\n').encode()
    def write(self, value): self.written.append(value)

def client(lines):
    c=Diagnostics.__new__(Diagnostics)
    c.port=Port(lines)
    c.log=io.StringIO()
    return c

def test_waits_for_matching_command_and_keeps_unsolicited_status():
    c=client(['BOARD:READY', 'DIAG '+json.dumps({'type':'status','connected':True}),
              'DIAG '+json.dumps({'type':'done','command':'DIAG:STATUS'}),
              'DIAG '+json.dumps({'type':'done','command':'DIAG:PROBE'})])
    results=c.command('DIAG:PROBE')
    assert results[0]['connected'] is True
    assert results[-1]['command']=='DIAG:PROBE'
    assert len(results)==3
    assert c.port.written==[b'DIAG:PROBE\n']

def test_fetch_preserves_binary_chunks():
    payload=bytes(range(256))
    c=client(['DIAG '+json.dumps({'type':'body','base64':base64.b64encode(payload).decode()}),
              'DIAG '+json.dumps({'type':'done','command':'DIAG:FETCH http://192.168.0.1/'})])
    results=c.command('DIAG:FETCH http://192.168.0.1/')
    assert base64.b64decode(results[0]['base64'])==payload

def test_corrupted_passive_line_does_not_abort_command():
    c=client(['DIAG {"type":"staDIAG {"type":"status"}',
              'DIAG '+json.dumps({'type':'done','command':'DIAG:STATUS'})])
    assert c.command('DIAG:STATUS')==[{'type':'done','command':'DIAG:STATUS'}]
