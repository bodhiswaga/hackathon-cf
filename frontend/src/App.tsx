import {useEffect,useState} from 'react'
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
import StatsPage from './components/StatsPage'
import {dateLabel} from './utils'
export default function App(){
 const [user,setUser]=useState<User|null>(null),[meta,setMeta]=useState<Meta|null>(null),[booting,setBooting]=useState(true),[error,setError]=useState(''),[notice,setNotice]=useState(''),[revision,setRevision]=useState(0),[page,setPage]=useState<Page>('search')
 useEffect(()=>{let active=true;setError('');setBooting(true);Promise.all([api<Meta>('/meta'),getToken()?api<User>('/auth/me'):Promise.resolve(null)]).then(([m,u])=>{if(active){setMeta(m);setUser(u);if(u)setPage(u.role==='admin'?'admin-bookings':'search')}}).catch(e=>{if(active){if(e.status===401){saveToken(null);setNotice('Сессия истекла. Войди снова.')}else setError(e.message)}}).finally(()=>{if(active)setBooting(false)});return()=>{active=false}},[revision])
 useEffect(()=>{const expired=()=>{saveToken(null);setUser(null);setNotice('Сессия истекла. Войди снова, чтобы продолжить.')};window.addEventListener('session-expired',expired);return()=>window.removeEventListener('session-expired',expired)},[])
 useEffect(()=>{const labels:Record<Page,string>={search:'Найти аудиторию',bookings:'Мои бронирования','admin-bookings':'Все бронирования',rooms:'Аудитории',stats:'Загрузка кампуса',plans:'Встречи и очередь',account:'Настройки профиля'};document.title=`${user?labels[page]:'Вход'} — CampusFlow`},[page,user])
 useEffect(()=>{window.scrollTo({top:0,left:0,behavior:'auto'});document.getElementById('main')?.focus({preventScroll:true})},[page])
 function auth(value:Auth){saveToken(value.accessToken);setUser(value.user);setPage(value.user.role==='admin'?'admin-bookings':'search');setNotice('');if(!meta)api<Meta>('/meta').then(setMeta).catch(e=>setError(e.message))}
 async function logout(){try{await api('/auth/logout',{method:'POST'});saveToken(null);setUser(null);setNotice('')}catch(e){setError((e as Error).message)}}
 async function refreshMeta(){try{setMeta(await api<Meta>('/meta'))}catch{/* next page load retries metadata */}}
 const meetingToken=new URLSearchParams(location.hash.slice(1)).get('meeting')
 if(meetingToken)return <SharedMeeting token={meetingToken}/>
 if(booting)return <div className="boot-screen"><span className="loading-ring"/><p>Открываем кампус…</p></div>
 if(error)return <div className="boot-screen"><RefreshCw size={30}/><h1>Не удалось подключиться</h1><p>{error}</p><button className="primary" onClick={()=>setRevision(v=>v+1)}>Повторить</button></div>
 if(!user)return <AuthScreen onAuth={auth} notice={notice} meta={meta}/>
 if(!meta)return <div className="boot-screen">Загружаем настройки кампуса…</div>
 return <div className="app-shell"><a className="skip-link" href="#main">Перейти к содержимому</a><Sidebar user={user} page={page} onNavigate={setPage} onLogout={logout}/><div className="main-shell"><header className="topbar"><span>{user.role==='admin'?'Панель администратора':'Бронирование аудиторий'}</span><div><span className="topbar-date">{dateLabel(meta.today,{day:'numeric',month:'long',year:'numeric'})}</span><ThemeToggle/></div></header><main id="main" tabIndex={-1} className="page-content" key={page}>{page==='plans'&&user.role==='student'?<PlanningPage meta={meta}/>:page==='search'&&user.role==='student'?<RoomSearch meta={meta}/>:page==='account'?<AccountPage user={user} onUser={setUser} onSignedOut={message=>{saveToken(null);setUser(null);setNotice(message)}}/>:page==='bookings'?<BookingsPage meta={meta} onSearch={()=>setPage('search')}/>:page==='admin-bookings'&&user.role==='admin'?<BookingsPage meta={meta} admin onSearch={()=>setPage('rooms')}/>:page==='rooms'&&user.role==='admin'?<AdminRooms meta={meta} onChanged={refreshMeta}/>:page==='stats'&&user.role==='admin'?<StatsPage meta={meta}/>:null}</main><footer className="app-footer"><span>CampusFlow</span><span>{meta.demo?'Учебный кампус · Демонстрационные данные':'Бронирование аудиторий кампуса'}</span></footer></div></div>
}
