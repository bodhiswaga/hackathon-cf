import {useEffect,useState} from 'react'
import QRCode from 'qrcode'
import {api} from '../api'
import type {Interval,Room} from '../types'
import {roomName} from '../utils'
type Data={room:Room;date:string;now:string;freeSlots:Interval[];restrictions:{startTime:string;endTime:string;equipment:string[]}[]}
export function RoomQr({room}:{room:Room}){
 const [image,setImage]=useState(''),[error,setError]=useState('');const url=location.origin+'/#room='+room.id
 useEffect(()=>{let active=true;QRCode.toDataURL(url,{width:240,margin:2,color:{dark:'#292421',light:'#FFFFFF'}}).then(v=>{if(active)setImage(v)}).catch(()=>{if(active)setError('Не удалось создать QR-код.')});return()=>{active=false}},[url])
 return <details><summary>QR-код аудитории</summary>{image&&<a href={image} download={'campusflow-'+room.id+'.png'}><img width={180} height={180} src={image} alt={'Скачать QR-код '+roomName(room)}/></a>}{error&&<p>{error}</p>}<p><a href={url} target="_blank" rel="noreferrer">Открыть страницу аудитории</a></p></details>
}
export default function PublicRoom({id}:{id:string}){
 const [data,setData]=useState<Data|null>(null),[error,setError]=useState('')
 useEffect(()=>{let active=true;const load=()=>api<Data>('/public/rooms/'+encodeURIComponent(id)).then(d=>{if(active){setData(d);setError('')}}).catch(e=>{if(active)setError(e.message)});void load();const t=setInterval(()=>{if(!document.hidden)void load()},20000);return()=>{active=false;clearInterval(t)}},[id])
 return <main className="shared-meeting"><a href="/">CampusFlow</a><h1>{data?'Аудитория '+roomName(data.room):'Аудитория'}</h1>{error&&<p className="error" role="alert">{error}</p>}{data&&<section className="plan-card"><p>{data.room.capacity} мест · {data.room.floor} этаж</p><h2>{data.freeSlots.some(s=>s.startTime<=data.now&&s.endTime>data.now)?'Сейчас свободна':'Сейчас недоступна'}</h2><p>{data.date} · Екатеринбург, UTC+5</p><h3>Свободное время сегодня</h3>{data.freeSlots.filter(s=>s.endTime>data.now).map(s=><p key={s.startTime}>{s.startTime<data.now?data.now:s.startTime}–{s.endTime}</p>)}{data.restrictions.length>0&&<p>Есть временные ограничения помещения или оборудования. Доступность проверяется при бронировании.</p>}<a className="primary" href={'/#book-room='+data.room.id}>Войти и забронировать</a><p className="muted">Начать, продлить или завершить свою встречу можно в «Моих бронированиях».</p></section>}</main>
}
