import {useEffect,useState} from 'react'
import {flushSync} from 'react-dom'
import {RefreshCw} from 'lucide-react'
import {api,saveToken,getToken} from './api'
import type {Auth,Meta,User} from './types'
import Sidebar,{type Page} from './components/Sidebar'
import ThemeToggle from './components/ThemeToggle'
import AuthScreen from './components/AuthScreen'
import RoomSearch from './components/RoomSearch'
import BookingsPage from './components/BookingsPage'
import AdminRooms from './components/AdminRooms'
import AccountPage from './components/AccountPage'
import PlanningPage, {SharedMeeting} from './components/PlanningPage'
import CommunityPage from './components/CommunityPage'
import {VerifyEmail} from './components/EmailSettings'
import StatsPage from './components/StatsPage'
import PublicRoom from './components/PublicRoom'
import {dateLabel} from './utils'
export default function App(){
 const [hash,setHash]=useState(()=>location.hash)
 useEffect(()=>{const changed=()=>setHash(location.hash);window.addEventListener('hashchange',changed);return()=>window.removeEventListener('hashchange',changed)},[])
 const hashParams=new URLSearchParams(hash.slice(1))
 const verificationPage=hashParams.has('verify-email')
 const verificationToken=hashParams.get('verify-email')||''
 const meetingToken=hashParams.get('meeting')
 function navigate(nextPage:Page){if(nextPage===page)return;if(document.startViewTransition&&!matchMedia('(prefers-reduced-motion: reduce)').matches){document.startViewTransition(()=>flushSync(()=>setPage(nextPage)))}else setPage(nextPage)}
 const [user,setUser]=useState<User|null>(null),[meta,setMeta]=useState<Meta|null>(null),[booting,setBooting]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[revision,setRevision]=useState(0),[page,setPage]=useState<Page>('search')
 useEffect(()=>{let active=true;setError('');setBooting(true);Promise.all([api<Meta>('/meta'),getToken()?api<User>('/auth/me'):Promise.resolve(null)]).then(([m,u])=>{if(active){setMeta(m);setUser(u);if(u)setPage(u.role==='admin'?'admin-bookings':location.hash.includes('team=')?'community':'search')}}).catch(e=>{if(active){if(e.status===401){saveToken(null);setNotice('Сессия истекла. Войди снова.')}else setError(e.message)}}).finally(()=>{if(active)setBooting(false)});return()=>{active=false}},[revision])
 useEffect(()=>{const expired=()=>{saveToken(null);setUser(null);setNotice('Сессия истекла. Войди снова, чтобы продолжить.')};window.addEventListener('session-expired',expired);return()=>window.removeEventListener('session-expired',expired)},[])
 useEffect(()=>{const labels:Record<Page,string>={search:'Найти аудиторию',bookings:'Мои бронирования','admin-bookings':'Все бронирования',rooms:'Аудитории',stats:'Загрузка кампуса',community:'Команды и встречи',plans:'Встречи и очередь',account:'Настройки профиля'};document.title=`${verificationPage?'Подтверждение email':meetingToken?'Встреча команды':user?labels[page]:'Вход'} — CampusFlow`},[page,user,verificationPage,meetingToken])
 useEffect(()=>{window.scrollTo({top:0,left:0,behavior:'auto'});document.getElementById('main')?.focus({preventScroll:true})},[page])
 function auth(value:Auth){saveToken(value.accessToken);setUser(value.user);setPage(value.user.role==='admin'?'admin-bookings':location.hash.includes('team=')?'community':'search');setNotice('');if(!meta)api<Meta>('/meta').then(setMeta).catch(e=>setError(e.message))}
 async function logout(){try{await api('/auth/logout',{method:'POST'});saveToken(null);setUser(null);setNotice('')}catch(e){setError((e as Error).message)}}
 async function refreshMeta(){try{setMeta(await api<Meta>('/meta'))}catch{/* next page load retries metadata */}}
 useEffect(()=>{let active=true;const timer=setInterval(()=>{if(!document.hidden)api<Meta>('/meta').then(m=>{if(active)setMeta(m)}).catch(()=>{})},30000);return()=>{active=false;clearInterval(timer)}},[])
 if(hashParams.has('room'))return <PublicRoom id={hashParams.get('room')||''}/>
 if(verificationPage)return <VerifyEmail token={verificationToken} key={verificationToken}/>
 if(meetingToken)return <SharedMeeting token={meetingToken}/>
 if(booting)return <div className="boot-screen"><span className="loading-ring"/><p>Открываем кампус…</p></div>
 if(error)return <div className="boot-screen"><RefreshCw size={30}/><h1>Не удалось подключиться</h1><p>{error}</p><button className="primary" onClick={()=>setRevision(v=>v+1)}>Повторить</button></div>
 if(!user)return <AuthScreen onAuth={auth} notice={notice} meta={meta}/>
 if(!meta)return <div className="boot-screen">Загружаем настройки кампуса…</div>
 return <div className="app-shell"><a className="skip-link" href="#main">Перейти к содержимому</a><Sidebar user={user} page={page} onNavigate={navigate} onLogout={logout}/><div className="main-shell"><header className="topbar"><span>{user.role==='admin'?'Панель администратора':'Бронирование аудиторий'}</span><div><span className="topbar-date">{dateLabel(meta.today,{day:'numeric',month:'long',year:'numeric'})}</span><ThemeToggle/></div></header><main id="main" tabIndex={-1} className="page-content" key={page}>{page==='community'&&user.role==='student'?<CommunityPage user={user} meta={meta}/>:page==='plans'&&user.role==='student'?<PlanningPage meta={meta}/>:page==='search'&&user.role==='student'?<RoomSearch meta={meta}/>:page==='account'?<AccountPage user={user} onUser={setUser} onSignedOut={message=>{saveToken(null);setUser(null);setNotice(message)}}/>:page==='bookings'?<BookingsPage meta={meta} onSearch={()=>navigate('search')}/>:page==='admin-bookings'&&user.role==='admin'?<BookingsPage meta={meta} admin onSearch={()=>navigate('rooms')}/>:page==='rooms'&&user.role==='admin'?<AdminRooms meta={meta} onChanged={refreshMeta}/>:page==='stats'&&user.role==='admin'?<StatsPage meta={meta}/>:null}</main><footer className="app-footer"><span>CampusFlow</span><span>{meta.demo?'Учебный кампус · Демонстрационные данные':'Бронирование аудиторий кампуса'}</span></footer></div></div>
}
