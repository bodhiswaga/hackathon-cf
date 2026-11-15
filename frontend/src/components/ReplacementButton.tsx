import {useState} from 'react'
import {api,downloadIcs} from '../api'
import type {Booking,Room} from '../types'
import Dialog from './Dialog'
import {roomName} from '../utils'

export default function ReplacementButton({booking,onChanged}:{booking:Booking;onChanged:()=>void}){
 const [open,setOpen]=useState(false),[rooms,setRooms]=useState<Room[]>([]),[busy,setBusy]=useState(false),[error,setError]=useState(''),[done,setDone]=useState<Booking|null>(null)
 async function load(){setOpen(true);setBusy(true);setError('');try{setRooms(await api(`/bookings/${booking.id}/alternatives`))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 async function replace(room:Room){setBusy(true);setError('');try{const b=await api<Booking>(`/bookings/${booking.id}/replace`,{method:'POST',body:JSON.stringify({slot:0,roomId:room.id})});setDone(b)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 return <><button className="secondary" onClick={()=>void load()}>Найти замену</button>{open&&<Dialog title="Подстраховка встречи" onClose={()=>{if(!busy){setOpen(false);if(done)onChanged()}}}><div className="confirm-body"><p>{booking.date} · {booking.startTime}–{booking.endTime}</p><p className="muted">Та же вместимость и оборудование. Сначала — ближайшие варианты в исходном корпусе.</p>{error&&<p className="error" role="alert">{error}</p>}{done?<><p className="notice">Забронирована {roomName(done.room)}. Исходная запись сохранена в истории.</p><button className="secondary" onClick={()=>downloadIcs(done)}>Обновить календарь</button></>:busy?<p role="status">Проверяем доступность…</p>:rooms.length?rooms.map(r=><div className="plan-option" key={r.id}><h3>{roomName(r)}</h3><p className="muted">{r.floor} этаж · {r.capacity} мест</p><button className="primary" disabled={busy} onClick={()=>void replace(r)}>Подтвердить замену</button></div>):<p className="muted">На это время подходящих аудиторий нет. Измени время через поиск.</p>}</div></Dialog>}</>
}
