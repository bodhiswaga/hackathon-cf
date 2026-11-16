import test from 'node:test'
import assert from 'node:assert/strict'
import {mailPreview} from '../src/mail-history.ts'
import {accounts,remember,forget,validateAccount} from '../src/accounts.ts'
test('mail preview limits and exact 15-minute boundary',()=>{
 const date='2026-11-16T12:00:00+05:00',now=Date.parse(date)
 const items=Array.from({length:4},(_,id)=>({id,createdAt:date}))
 assert.equal(mailPreview(items.slice(0,3),now).items.length,3)
 assert.equal(mailPreview(items,now+899999).items.length,1)
 assert.equal(mailPreview(items,now+900000).items.length,0)
 assert.equal(mailPreview(items.map(i=>({...i,sentAt:new Date(now+900000).toISOString()})),now+900000).expired,false)
 assert.equal(mailPreview([{id:1}],now).expired,true)
})
test('account store deduplicates, forgets and rejects revoked tokens',async()=>{
 const storage=new Map()
 globalThis.sessionStorage={getItem:k=>storage.get(k)??null,setItem:(k,v)=>storage.set(k,v)}
 const auth=id=>({user:{id,login:'user'+id},accessToken:'token'+id})
 remember(auth(1));remember(auth(2));remember(auth(1))
 assert.deepEqual(accounts().map(a=>a.user.id),[1,2])
 globalThis.fetch=async()=>({status:401,ok:false})
 await assert.rejects(validateAccount(accounts()[1]),/истекла/)
 assert.deepEqual(accounts().map(a=>a.user.id),[1])
 forget(1);assert.equal(accounts().length,0)
})
