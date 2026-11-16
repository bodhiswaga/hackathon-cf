import {useEffect,useState} from 'react'
import {api} from '../api'
import {mailPreview} from '../mail-history'
import {ArrowLeft, Check, Mail, TriangleAlert, CircleAlert, ChevronDown, ChevronRight} from 'lucide-react'
import {Brand} from './Sidebar'
import ThemeToggle from './ThemeToggle'
type Delivery={id:number;subject:string;state:string;error:string;nextAttempt?:string;createdAt?:string;sentAt?:string}
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
export function MailHistory({deliveries,onRefresh,busy}:{deliveries:Delivery[];onRefresh:()=>void;busy:boolean}){
 const [expanded,setExpanded]=useState(false),[history,setHistory]=useState<Delivery[]>([]),[more,setMore]=useState(false),[loading,setLoading]=useState(false),[error,setError]=useState(''),[now,setNow]=useState(Date.now())
 useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer)},[])
 const preview=mailPreview(deliveries,now), expired=preview.expired
 useEffect(()=>{if(expired)setExpanded(false)},[expired])
 async function load(before?:number){setLoading(true);setError('');try{const r=await api<{items:Delivery[];hasMore:boolean}>('/email/history'+(before?'?before='+before:''));setHistory(v=>before?[...v,...r.items]:r.items);setMore(r.hasMore)}catch(e){setError((e as Error).message)}finally{setLoading(false)}}
 const shown=expanded?history:preview.items
 return <div className="email-deliveries"><div className="mail-history-heading"><h3>Последние письма</h3><button type="button" className="secondary" disabled={busy} onClick={()=>{onRefresh();if(expanded)void load()}}>Обновить статус</button></div>{deliveries.length>0&&<button className="mail-history-toggle" aria-expanded={expanded} aria-controls="mail-history" onClick={()=>{setExpanded(v=>!v);if(!expanded)void load()}}>{expanded?<ChevronDown size={17}/>:<ChevronRight size={17}/>}Посмотреть все</button>}{error&&<p className="error" role="alert">{error}</p>}<div id="mail-history" className={expanded?'mail-history-list expanded':'mail-history-list'}>{shown.map(d=><div className="mail-delivery" key={d.id}><div><strong>{d.subject}</strong>{d.sentAt?<time dateTime={d.sentAt}>Отправлено {mailDate(d.sentAt)}</time>:<span className="field-hint">{d.state==='sent'?'Время отправки не сохранено':d.createdAt?'Создано '+mailDate(d.createdAt):'Дата неизвестна'}</span>}</div><span>{states[d.state]||d.state}</span>{d.error==='QUOTA_EXCEEDED'&&<p className="muted">Квота Google исчерпана. Письмо ожидает следующей попытки.</p>}{d.error==='DELIVERY_UNCERTAIN'&&<p className="muted">Результат отправки не подтверждён. Оператор должен проверить доставку перед повтором.</p>}</div>)}{expanded&&loading&&<p role="status">Загружаем историю…</p>}{expanded&&more&&<button className="secondary" disabled={loading} onClick={()=>void load(history.at(-1)?.id)}>Ещё письма</button>}</div>{!deliveries.length&&<p className="muted">Писем пока нет.</p>}<p className="field-hint">Время Екатеринбурга, UTC+5. Статус отправки не гарантирует попадание во входящие. Проверь также папку «Спам».</p></div>
}
function mailDate(value:string){return new Intl.DateTimeFormat('ru-RU',{timeZone:'Asia/Yekaterinburg',day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(new Date(value))}
export default function EmailSettings(){
 const [settings,setSettings]=useState<Settings|null>(null),[email,setEmail]=useState(''),[prefs,setPrefs]=useState<Record<string,boolean>>({meeting:true,team:true,queue:true,reminder:true}),[error,setError]=useState(''),[notice,setNotice]=useState(''),[busy,setBusy]=useState(false)
 useEffect(()=>{let active=true;api<Settings>('/email').then(s=>{if(active){setSettings(s);setEmail(s.email);setPrefs(v=>({...v,...s.preferences}))}}).catch(e=>{if(active)setError(e.message)});const refresh=()=>{api<Settings>('/email').then(s=>{if(active)setSettings(s)}).catch(()=>{})};const visible=()=>{if(!document.hidden)refresh()};window.addEventListener('focus',refresh);document.addEventListener('visibilitychange',visible);return()=>{active=false;window.removeEventListener('focus',refresh);document.removeEventListener('visibilitychange',visible)}},[])
 const currentEmail=email.trim()
 const changed=Boolean(settings&&currentEmail!==settings.email)
 const verified=Boolean(settings?.verified&&!changed&&currentEmail)
 const statusText=!currentEmail?'Email не указан':changed?'Новый адрес — не подтверждён':verified?'Подтверждён':'Не подтверждён'
 const StatusIcon=verified?Check:currentEmail?CircleAlert:Mail
 return <section className="plan-card email-settings"><div className="email-section-heading"><h2>Почтовые уведомления</h2>{settings&&<span className={`email-verification-badge ${verified?'verified':currentEmail?'unverified':'empty'}`} role="status"><StatusIcon size={15} aria-hidden="true"/>{statusText}</span>}</div>{error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice" role="status">{notice}</p>}{settings&&!settings.configured?<p className="muted">Отправка писем пока не подключена. После настройки отправителя здесь можно подтвердить email и выбрать уведомления.</p>:settings?<form onSubmit={async e=>{e.preventDefault();setBusy(true);setError('');try{const r=await api<{verificationRequired:boolean}>('/email',{method:'PUT',body:JSON.stringify({email,...prefs})});setSettings(await api<Settings>('/email'));setNotice(r.verificationRequired?'Письмо подтверждения поставлено в очередь. Ссылка действует час.':'Настройки сохранены.')}catch(e){setError((e as Error).message)}finally{setBusy(false)}}}><label>Email<input type="email" required maxLength={254} value={email} onChange={e=>setEmail(e.target.value)}/></label><p className="muted">{verified?'Уведомления будут отправляться на этот адрес.':changed?'Сохрани новый адрес и подтверди его по ссылке из письма.':'Открой письмо CampusFlow и подтверди адрес по ссылке.'}</p>{Object.entries(labels).map(([key,label])=><label className="plan-check" key={key}><input type="checkbox" checked={prefs[key]} onChange={e=>setPrefs(v=>({...v,[key]:e.target.checked}))}/>{label}</label>)}<button className="primary" disabled={busy}>Сохранить</button></form>:<p>Загружаем настройки…</p>}{settings&&<MailHistory deliveries={settings.deliveries||[]} busy={busy} onRefresh={()=>{setBusy(true);api<Settings>('/email').then(setSettings).catch(e=>setError(e.message)).finally(()=>setBusy(false))}}/>}</section>
}
