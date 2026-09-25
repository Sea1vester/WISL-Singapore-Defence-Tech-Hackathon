import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';
import {runInNewContext} from 'node:vm';

const source=readFileSync(new URL('../scripts/fetch-cesium.cjs',import.meta.url),'utf8');
function install(platform,fail=false){
  const calls=[],copies=[],cleanups=[];
  const paths=platform==='win32'?path.win32:path.posix;
  const fs={existsSync:()=>false,mkdtempSync:prefix=>prefix+'test',mkdirSync(){},cpSync:(...args)=>copies.push(args),readdirSync:()=>[],rmSync:(...args)=>cleanups.push(args)};
  let error;
  try{runInNewContext(source,{
    __dirname:platform==='win32'?'C:\\Work with spaces\\sdth-replay\\scripts':'/work with spaces/sdth-replay/scripts',
    process:{platform,env:{}},console:{log(){}},
    require(name){return {'node:fs':fs,'node:os':{tmpdir:()=>platform==='win32'?'C:\\Temp space':'/tmp space'},'node:path':paths,'node:child_process':{execFileSync(command,args,options){calls.push({command,args,options});if(fail)throw new Error('download failed');}}}[name];},
  });}catch(e){error=e;}
  return {calls,copies,cleanups,error};
}

test('Windows vendoring uses PowerShell and native Node copying, not Unix utilities',()=>{
  const result=install('win32');
  assert.equal(result.error,undefined);
  assert.equal(result.calls[0].command,'curl');
  assert.equal(result.calls[1].command,'powershell.exe');
  assert.ok(result.calls[1].args.includes('-NoProfile'));
  assert.match(result.calls[1].args.at(-1),/Expand-Archive -LiteralPath/);
  assert.ok(result.calls[1].options.env.WISL_CESIUM_ARCHIVE.endsWith('cesium.zip'));
  assert.ok(result.calls.every(call=>!['rsync','unzip'].includes(call.command)));
  assert.equal(result.copies.length,1);
  assert.equal(result.cleanups.length,1);
});

test('Unix vendoring keeps unzip but does not require rsync',()=>{
  const result=install('darwin');
  assert.equal(result.error,undefined);
  assert.ok(result.calls.some(call=>call.command==='unzip'));
  assert.ok(result.calls.every(call=>call.command!=='rsync'));
  assert.equal(result.copies.length,1);
});

test('failed downloads clean up only their temporary staging directory',()=>{
  const result=install('win32',true);
  assert.match(result.error.message,/download failed/);
  assert.equal(result.copies.length,0);
  assert.equal(result.cleanups.length,1);
  assert.match(result.cleanups[0][0],/cesium-test$/);
});
