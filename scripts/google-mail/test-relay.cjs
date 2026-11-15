// Executes the actual Apps Script source with in-memory Google service doubles.
const fs = require('node:fs');
const vm = require('node:vm');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const store = {'CAMPUSFLOW_MAIL_SECRET':'s'.repeat(40)};
let quota = 100, sends = 0, throwOnSend = false, locked = false;
const context = {
  console, Date, JSON,
  PropertiesService:{getScriptProperties:()=>({getProperty:k=>store[k]||null,setProperty:(k,v)=>store[k]=v,deleteProperty:k=>delete store[k],getProperties:()=>({...store})})},
  Utilities:{Charset:{UTF_8:'utf8'},DigestAlgorithm:{SHA_256:'sha256'},computeHmacSha256Signature:(v,k)=>[...crypto.createHmac('sha256',k).update(v).digest()],computeDigest:(_,v)=>[...crypto.createHash('sha256').update(v).digest()]},
  ContentService:{MimeType:{JSON:'json'},createTextOutput:value=>({setMimeType:()=>value})},
  LockService:{getScriptLock:()=>({tryLock:()=>!locked,releaseLock:()=>{}})},
  MailApp:{getRemainingDailyQuota:()=>quota,sendEmail:m=>{assert.equal(m.name,'CampusFlow');sends++;if(throwOnSend)throw Error('uncertain');quota--;}}
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(require('node:path').join(__dirname,'Code.gs'),'utf8'),context);
function envelope(id='a'.repeat(64),changes={},time=Math.floor(Date.now()/1000)) {
 const payload=JSON.stringify({id,to:'test@example.com',subject:'Встреча',text:'Екатеринбург',...changes});
 return {timestamp:time,payload,signature:crypto.createHmac('sha256',store.CAMPUSFLOW_MAIL_SECRET).update(time+'\n'+payload).digest('hex')};
}
function post(e){return JSON.parse(context.doPost({postData:{contents:JSON.stringify(e)}}));}
assert.equal(post({...envelope(),signature:'0'.repeat(64)}).code,'AUTH_FAILED');
assert.equal(post(envelope('a'.repeat(64),{},1)).code,'AUTH_FAILED');
assert.equal(post(envelope('a'.repeat(64),{to:'a@example.com,b@example.com'})).code,'INVALID_MESSAGE');
assert.equal(post(envelope()).ok,true);assert.equal(sends,1);
assert.equal(post(envelope()).duplicate,true);assert.equal(sends,1);
assert.equal(post(envelope('a'.repeat(64),{text:'changed'})).code,'ID_CONFLICT');
quota=0;assert.equal(post(envelope('b'.repeat(64))).code,'QUOTA_EXCEEDED');assert.equal(sends,1);
quota=99;assert.equal(post(envelope('b'.repeat(64))).ok,true);assert.equal(sends,2);
throwOnSend=true;assert.equal(post(envelope('c'.repeat(64))).code,'DELIVERY_UNCERTAIN');assert.equal(sends,3);
throwOnSend=false;assert.equal(post(envelope('c'.repeat(64))).code,'DELIVERY_UNCERTAIN');assert.equal(sends,3);
locked=true;assert.equal(post(envelope('d'.repeat(64))).code,'BUSY');
console.log('Apps Script protocol: signature, expiry, recipient, deduplication, quota, ambiguity and lock checks passed');
