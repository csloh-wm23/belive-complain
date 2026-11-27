"""SDK callback regression without a browser or real Meta requests."""
import shutil
import subprocess
import unittest
from pathlib import Path

@unittest.skipUnless(shutil.which('node'),'Node.js is required for JavaScript checks')
class MetaJavascriptTests(unittest.TestCase):
    def test_completed_session_reload_does_not_restart_authorisation(self):
        source=Path(__file__).resolve().parents[1]/'assets/meta-signup.js'
        script=r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements=Object.fromEntries(['status','connect','finish','identity'].map(k=>[k,{textContent:'',disabled:true}]));
const ctx={location:{hash:'',pathname:'/connect/whatsapp'},history:{replaceState(){}},
fetch:async()=>({ok:true,json:async()=>({csrf:'qa',ready:true,connected:true,app_id:'123456',config_id:'234567'})}),
document:{getElementById:k=>elements[k],createElement(){throw Error('Completed session must not reload SDK');}},
addEventListener(){}};
ctx.window=ctx;vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
setImmediate(()=>{assert.match(elements.status.textContent,/setup completed/);assert.match(elements.status.textContent,/not yet been confirmed/);assert.equal(elements.connect.disabled,true);assert.equal(elements.finish.hidden,true);});
'''
        result=subprocess.run(['node','-e',script,str(source)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

    def test_sdk_receives_regular_callback_and_sync_errors_allow_retry(self):
        source=Path(__file__).resolve().parents[1]/'assets/meta-signup.js'
        script=r'''
const vm=require('node:vm'),fs=require('node:fs'),assert=require('node:assert/strict');
const elements=Object.fromEntries(['status','connect','finish','identity'].map(k=>[k,{textContent:'',disabled:true}]));
let shouldThrow=false,captured,timer;
const ctx={console,location:{hash:'',pathname:'/connect/whatsapp'},history:{replaceState(){}},
  setTimeout:fn=>{timer=fn},fetch:async()=>({ok:true,json:async()=>({csrf:'qa-csrf',ready:true,app_id:'123456',config_id:'234567',graph_version:'v27.0'})}),
  document:{getElementById:k=>elements[k],createElement:()=>({}),head:{appendChild:()=>ctx.fbAsyncInit()}},
  addEventListener(){},FB:{init(){},login(cb,options){assert.equal(cb.constructor.name,'Function');captured=options;if(shouldThrow)throw Error('QA popup blocked');}}};
ctx.window=ctx;vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
setImmediate(()=>{assert.equal(elements.connect.disabled,false);elements.connect.onclick();assert.equal(captured.config_id,'234567');assert.equal(captured.extras.featureType,'whatsapp_business_app_onboarding');timer();assert.equal(elements.connect.disabled,false);assert.match(elements.status.textContent,/blocked/);shouldThrow=true;elements.connect.onclick();assert.equal(elements.connect.disabled,false);assert.match(elements.status.textContent,/QA popup blocked/);console.log('PASS: ordinary SDK callback, timeout recovery and synchronous error recovery.');});
'''
        result=subprocess.run(['node','-e',script,str(source)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
