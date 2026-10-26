from pathlib import Path
from contextlib import closing
import json,sys,shutil,sqlite3,hashlib
ROOT=Path.cwd();sys.path[:0]=[str(ROOT/'tests'),str(ROOT/'scripts')]
import forestry_mission_api as t
import workshop_api as api
run=ROOT/'.local/iter0028/python/20261026T104048Z-e1a5b3/test_01_actual_cli_two_generations_restart_and_wood_use'
source=run/'runtime';data=ROOT/'.local/iter0028/python-cold-restart-runtime'
api.DLL=ROOT/'.local/iter0028/server-v2/World.Server.dll'
world=t.World(data,source)
world.access=json.loads((data/'access.json').read_text());world.instance='w_15ced6889f624d8da8a3d2129ba26874'
result={'source':str(source.relative_to(ROOT)),'sourceSha256':t.digest(source/'world.db'),'dllSha256':t.digest(api.DLL),'entries':[]}
success=False
try:
    initial=t.snapshot(data)
    world.start()
    before=world.request('GET',api.PREFIX+'/observation',actor='a3',capability=t.SUPPORTED_CAPABILITIES)
    assert before[0]==200
    assert (before[1]['self']['inventory']['wood'],before[1]['forestry']['seeds'])==(3,1)
    assert before[1]['resourceAudit']['conserved'] and before[1]['seedAudit']['conserved']
    world.restart()
    for report in json.loads((run/'reports.json').read_text()):
        for step in report['steps']:
            if step['action']['type'] not in t.forestry.PERMISSIONS:continue
            receipt=world.request('GET',api.PREFIX+'/commands/'+step['commandId'],actor='a3',capability=t.SUPPORTED_CAPABILITIES)
            replay=world.request('POST',api.PREFIX+'/commands',step['request'],actor='a3',capability=t.SUPPORTED_CAPABILITIES)
            assert receipt[0]==replay[0]==200
            assert receipt[1]==step['receipt']
            assert receipt[2]==replay[2]
            result['entries'].append({'commandId':step['commandId'],'action':step['action'],'originalReceiptSame':True,'replayedBytesSame':True})
    after=world.request('GET',api.PREFIX+'/observation',actor='a3',capability=t.SUPPORTED_CAPABILITIES)[1]
    assert before[1]['self']==after['self'] and before[1]['forestry']['seeds']==after['forestry']['seeds']
    assert before[1]['resourceAudit']==after['resourceAudit'] and before[1]['seedAudit']==after['seedAudit']
    world.stop()
    final=t.snapshot(data)
    tables=('entities','entity_canvas','entity_canvas_cells','entity_canvas_edits','entity_note_adoption','entity_notes','world_instance','receipts','events','resource_ledger','forestry_actions','forestry_plants','forestry_reservations','forestry_seeds','forestry_tools')
    retained={name:initial[name]==final[name] for name in tables};assert all(retained.values())
    with closing(sqlite3.connect(f'file:{data/"world.db"}?mode=ro',uri=True)) as db:
        integrity=db.execute('PRAGMA integrity_check').fetchall();foreign=db.execute('PRAGMA foreign_key_check').fetchall()
    assert integrity==[('ok',)] and foreign==[]
    result.update(passed=True,resourceAudit=after['resourceAudit'],seedAudit=after['seedAudit'],originalTablesUnchanged=retained,integrity=integrity,foreignKeys=foreign)
    success=True
finally:
    world.stop()
    result['processExited']=world.process is None or world.process.poll() is not None
    if (data/'server.log').exists():shutil.copy2(data/'server.log',run/'cold-restart-server.log')
    if success:shutil.rmtree(data)
    result['diagnosticCopyRemoved']=not data.exists()
    result['originalSourceBytesUnchanged']=result['sourceSha256']==t.digest(source/'world.db')
    t.save(run/'cold-restart-summary.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('entries','originalTablesUnchanged')},ensure_ascii=False))
