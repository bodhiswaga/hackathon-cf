export const dateLabel = (date:string, options:Intl.DateTimeFormatOptions={day:'numeric',month:'long'}) => new Date(date+'T12:00:00').toLocaleDateString('ru-RU',options)
export const addDays = (date:string, days:number) => { const value=new Date(date+'T12:00:00');value.setDate(value.getDate()+days);return localDate(value) }
export const localDate = (date:Date) => `${date.getFullYear()}-${String(date.getMonth()+1).padStart(2,'0')}-${String(date.getDate()).padStart(2,'0')}`
export const toMinutes = (value:string)=>Number(value.slice(0,2))*60+Number(value.slice(3))
export const toTime = (value:number)=>`${String(Math.floor(value/60)).padStart(2,'0')}:${String(value%60).padStart(2,'0')}`
export const roomName = (room:{building:string;name:string})=>`${room.building}-${room.name}`
