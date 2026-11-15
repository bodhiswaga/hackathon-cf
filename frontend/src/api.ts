import type { Booking } from './types'
const KEY = 'campus-session-v1'
export const getToken = () => sessionStorage.getItem(KEY)
export const saveToken = (token: string | null) => token ? sessionStorage.setItem(KEY, token) : sessionStorage.removeItem(KEY)
export class ApiError extends Error { constructor(message:string, public status:number, public code:string){super(message)} }
export async function api<T>(path:string, init:RequestInit = {}):Promise<T> {
  const token = getToken()
  let response:Response
  try { response = await fetch('/api'+path, {...init, headers:{'Content-Type':'application/json', ...(token ? {Authorization:`Bearer ${token}`} : {}), ...init.headers}}) }
  catch {throw new ApiError('Нет связи с сервером. Проверьте подключение и повторите попытку.', 0, 'NETWORK')}
  if (!response.ok) {
    const data = await response.json().catch(()=>({}))
    if(response.status===401 && !['/auth/login','/auth/register'].includes(path)) window.dispatchEvent(new Event('session-expired'))
    throw new ApiError(data.error?.message || 'Не удалось выполнить запрос. Попробуйте ещё раз.', response.status, data.error?.code || 'ERROR')
  }
  return response.json()
}
export function downloadBlob(blob:Blob, name:string){const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download=name;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
export async function downloadCsv(){const response=await fetch('/api/admin/bookings.csv',{headers:{Authorization:`Bearer ${getToken()}`}});if(!response.ok)throw new Error('Не удалось загрузить CSV.');downloadBlob(await response.blob(),'campusflow-bookings.csv')}
export function downloadIcs(booking:Booking){
  const escape=(s:string)=>s.replace(/\\/g,'\\\\').replace(/\n/g,'\\n').replace(/,/g,'\\,').replace(/;/g,'\\;')
  const stamp=(time:string)=>booking.date.replace(/-/g,'')+'T'+time.replace(':','')+'00'
  const text=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//CampusFlow//RU','CALSCALE:GREGORIAN','BEGIN:VEVENT',`UID:booking-${booking.id}@campusflow`, `DTSTAMP:${new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d{3}/,'')}`,`DTSTART;TZID=Asia/Yekaterinburg:${stamp(booking.startTime)}`,`DTEND;TZID=Asia/Yekaterinburg:${stamp(booking.endTime)}`,`SUMMARY:${escape('Аудитория '+booking.room.building+'-'+booking.room.name)}`,`LOCATION:${escape('Корпус '+booking.room.building+', этаж '+booking.room.floor)}`,`DESCRIPTION:${escape(booking.comment)}`,'END:VEVENT','END:VCALENDAR'].join('\r\n')
  downloadBlob(new Blob([text],{type:'text/calendar;charset=utf-8'}),`campusflow-${booking.id}.ics`)
}
