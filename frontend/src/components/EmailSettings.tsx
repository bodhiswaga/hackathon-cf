import {useEffect,useState} from 'react'
import {api} from '../api'
import {ArrowLeft, Check, Mail, TriangleAlert, CircleAlert} from 'lucide-react'
import {Brand} from './Sidebar'
import ThemeToggle from './ThemeToggle'
type Delivery={id:number;subject:string;state:string;error:string;nextAttempt?:string}
const states:Record<string,string>={pending:'В очереди',processing:'Отправляется',sent:'Передано отправителю',failed:'Ошибка отправки',skipped:'Уже неактуально'}
type Settings={deliveries?:Delivery[];configured:boolean;email:string;verified:boolean;preferences:Record<string,boolean>}
const labels:Record<string,string>={meeting:'Встречи, отмены и переносы',team:'Вступление в команду',queue:'Предложения из очереди',reminder:'Напоминание за час'}
export function VerifyEmail({token}:{token:string}){
 const [state,setState]=useState<'ready'|'pending'|'success'|'error'>(token?'ready':'error')
 const [error,setError]=useState(token?'':'В ссылке нет кода подтверждения. Открой полную ссылку из письма или запроси новое письмо в профиле.')
 const success=state==='success'
 const Icon=success?Check:state==='error'?TriangleAlert:Mail
 async function confirm(){
  if(state==='pending'||success||!token)return
  setState('pending');setError('')
  try{await api('/email/verify',{method:'POST',body:JSON.stringify({token})});setState('success')}
  catch(e){setError((e as Error).message);setState('error')}
 }
 return <div className="verification-page">
  <header className="verification-header"><a href="/" aria-label="CampusFlow — на главную"><Brand/></a><ThemeToggle/></header>
  <main className="verification-main"><section className="verification-card" aria-labelledby="verification-title" aria-busy={state==='pending'}>
   <span className={`verification-icon ${success?'is-success':''}`} aria-hidden="true"><Icon size={26} strokeWidth={1.7}/></span>
   <div className="page-kicker">Почтовые уведомления</div>
   <h1 id="verification-title">{success?'Email подтверждён':'Подтверди свой email'}</h1>
   <p className="verification-description">{success?'Теперь ты сможешь получать уведомления о встречах и изменениях бронирований.':'Подтверди адрес, чтобы получать выбранные уведомления CampusFlow.'}</p>
   {error&&<p className="verification-error" role="alert">{error}</p>}
   {success?<a href="/" className="primary">Открыть CampusFlow</a>:<button className="primary" disabled={state==='pending'||!token} onClick={()=>void confirm()}>{state==='pending'?'Подтверждаем…':state==='error'&&token?'Попробовать снова':'Подтвердить email'}</button>}
   {!success&&<a className="verification-back" href="/"><ArrowLeft size={15}/>Вернуться в приложение</a>}
   <p className="verification-footnote" role={success?'status':undefined}>{success?'Настройки уведомлений доступны в профиле.':'Ссылка одноразовая и действует один час.'}</p>
  </section></main>
  <footer className="verification-footer">CampusFlow · Пространство для твоих планов</footer>
 </div>
}
export default function EmailSettings(){
 const [settings,setSettings]=useState<Settings|null>(null),[email,setEmail]=useState(''),[prefs,setPrefs]=useState<Record<string,boolean>>({meeting:true,team:true,queue:true,reminder:true}),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false)
 useEffect(()=>{let active=true;api<Settings>('/email').then(s=>{if(active){setSettings(s);setEmail(s.email);setPrefs(v=>({...v,...s.preferences}))}}).catch(e=>{if(active)setError(e.message)});const refresh=()=>{api<Settings>('/email').then(s=>{if(active)setSettings(s)}).catch(()=>{})};const visible=()=>{if(!document.hidden)refresh()};window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',visible);return()=>{active=false;window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',visible)}},[])
 const currentEmail=email.trim()
 const changed=Boolean(settings&&currentEmail!==settings.email)
 const verified=Boolean(settings?.verified&&!changed&&currentEmail)
 const statusText=!currentEmail?'Email не указан':changed?'Новый адрес — не подтверждён':verified?'Подтверждён':'Не подтверждён'
 const StatusIcon=verified?Check:currentEmail?CircleAlert:Mail
 return <section className="plan-card email-settings"><div className="email-section-heading"><h2>Почтовые уведомления</h2>{settings&&<span className={`email-verification-badge ${verified?'verified':currentEmail?'unverified':'empty'}`} role="status"><StatusIcon size={15} aria-hidden="true"/>{statusText}</span>}</div>{error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}{settings&&!settings.configured?<p className="muted">Отправка писем пока не подключена. После настройки отправителя здесь можно подтвердить email и выбрать уведомления.</p>:settings?<form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const r=await api<{verificationRequired:boolean}>('/email',{method:'PUT',body:JSON.stringify({email,...prefs})});setSettings(await api<Settings>('/email'));setNotice(r.verificationRequired?'Письмо подтверждения поставлено в очередь. Ссылка действует час.':'Настройки сохранены.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}><label>Email<input type="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)}/></label><p className="muted">{verified?'Уведомления будут отправляться на этот адрес.':changed?'Сохрани новый адрес и подтверди его по ссылке из письма.':'Открой письмо CampusFlow и подтверди адрес по ссылке.'}</p>{Object.entries(labels).map(([key,label])=><label className="plan-check" key={key}><input type="checkbox" checked={prefs[key]} onChange={e=>setPrefs(v=>({...v,[key]:e.target.checked}))}/>{label}</label>)}<button className="primary" disabled={busy}>Сохранить</button></form>:<p>Загружаем настройки…</p>}{settings&&<div className="email-deliveries"><div className="settings-actions"><h3>Последние письма</h3><button type="button" className="secondary" disabled={busy} onClick={async()=>{setBusy(true);try{setSettings(await api<Settings>('/email'))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}>Обновить статус</button></div>{settings.deliveries?.length?settings.deliveries.map(d=><div className="series-row" key={d.id}><span>{d.subject}</span><strong>{states[d.state]||d.state}</strong>{d.error==='QUOTA_EXCEEDED'&&<p className="muted">Квота Google исчерпана. Письмо ожидает следующей попытки.</p>}{d.error==='DELIVERY_UNCERTAIN'&&<p className="muted">Результат отправки не подтверждён. Оператор должен проверить доставку перед повтором.</p>}</div>):<p className="muted">Писем пока нет.</p>}<p className="field-hint">Статус отправки не гарантирует попадание во входящие. Проверь также папку «Спам».</p></div>}</section>
}
