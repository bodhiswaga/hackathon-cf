import type {Auth,User} from './types'
const VAULT='campus-accounts-v1'
export type SavedAccount={user:User;token:string}
export function accounts():SavedAccount[]{try{const items=JSON.parse(sessionStorage.getItem(VAULT)||'[]');return Array.isArray(items)?items.filter(a=>a?.user?.id&&typeof a.token==='string').slice(0,5):[]}catch{return []}}
export function remember(auth:Auth){sessionStorage.setItem(VAULT,JSON.stringify([{user:auth.user,token:auth.accessToken},...accounts().filter(a=>a.user.id!==auth.user.id)].slice(0,5)))}
export function forget(id:number){sessionStorage.setItem(VAULT,JSON.stringify(accounts().filter(a=>a.user.id!==id)))}
export async function validateAccount(account:SavedAccount):Promise<Auth>{
 const response=await fetch('/api/auth/me',{headers:{Authorization:'Bearer '+account.token}})
 if(response.status===401){forget(account.user.id);throw new Error('Сессия аккаунта истекла. Добавь аккаунт заново.')}
 if(!response.ok)throw new Error('Не удалось переключить аккаунт. Повтори попытку.')
 return {accessToken:account.token,user:await response.json()}
}
