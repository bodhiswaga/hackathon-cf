import {useRef,useState} from 'react'
import {Camera} from 'lucide-react'
import {api} from '../api'
import type {User} from '../types'
export function Avatar({user,className='avatar'}:{user:User;className?:string}){return <span className={className} aria-hidden="true">{user.avatar?<img src={user.avatar} alt=""/>:user.displayName.trim().split(/\s+/).slice(0,2).map(p=>p[0]).join('')}</span>}
export default function AvatarEditor({user,onUser}:{user:User;onUser:(u:User)=>void}){
 const input=useRef<HTMLInputElement>(null),[busy,setBusy]=useState(false),[error,setError]=useState('')
 async function upload(file?:File){if(!file)return;setError('');setBusy(true);try{
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>5*1024*1024)throw new Error('Выбери JPEG, PNG или WebP до 5 МБ.')
  const url=URL.createObjectURL(file)
  let image:HTMLImageElement
  try{image=await new Promise((resolve,reject)=>{const i=new Image();i.onload=()=>resolve(i);i.onerror=()=>reject(new Error('Не удалось прочитать изображение.'));i.src=url})}finally{URL.revokeObjectURL(url)}
  const canvas=document.createElement('canvas');canvas.width=canvas.height=192
  const context=canvas.getContext('2d');if(!context)throw new Error('Браузер не поддерживает обработку фото.')
  const side=Math.min(image.width,image.height);context.fillStyle='#ffffff';context.fillRect(0,0,192,192);context.drawImage(image,(image.width-side)/2,(image.height-side)/2,side,side,0,0,192,192)
  onUser(await api<User>('/auth/avatar',{method:'PUT',body:JSON.stringify({image:canvas.toDataURL('image/jpeg',0.8)})}))
 }catch(e){setError((e as Error).message)}finally{setBusy(false);if(input.current)input.current.value=''}}
 async function remove(){setBusy(true);setError('');try{onUser(await api<User>('/auth/avatar',{method:'PUT',body:JSON.stringify({image:''})}))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <div className="avatar-editor"><button className="avatar-edit-button" disabled={busy} aria-label="Изменить фотографию профиля" onClick={()=>input.current?.click()}><Avatar user={user} className="account-avatar"/><span className="avatar-camera"><Camera size={15}/></span></button><input ref={input} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={e=>void upload(e.target.files?.[0])}/>{busy&&<small role="status">Сохраняем фото…</small>}{user.avatar&&<button className="avatar-remove" disabled={busy} onClick={()=>void remove()}>Убрать фото</button>}{error&&<p className="error" role="alert">{error}</p>}</div>
}
