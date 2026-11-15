// Adapted from uiable / Sidebar 1, 21st.dev component demo 19371.
// Retains grouped navigation and active item structure; replaces catalog data with app routes.
import { useState } from 'react'
import { Search, CalendarDays, Building2, ChartNoAxesCombined, LogOut, Menu, X, MapPin, ChevronRight, UserRound } from 'lucide-react'
import type { User } from '../types'
export type Page = 'search'|'bookings'|'admin-bookings'|'rooms'|'stats'|'account'
export default function Sidebar({user,page,onNavigate,onLogout}:{user:User;page:Page;onNavigate:(page:Page)=>void;onLogout:()=>void}){
  const [open,setOpen]=useState(false)
  const sections = user.role==='admin' ? [{title:'Управление кампусом',items:[{id:'admin-bookings' as Page,title:'Все бронирования',icon:CalendarDays},{id:'rooms' as Page,title:'Аудитории',icon:Building2},{id:'stats' as Page,title:'Загрузка кампуса',icon:ChartNoAxesCombined}]}] : [{title:'Мой кампус',items:[{id:'search' as Page,title:'Найти аудиторию',icon:Search},{id:'bookings' as Page,title:'Мои бронирования',icon:CalendarDays}]}]
  return <><div className="mobile-bar"><Brand/><button className="icon-button" aria-label={open?'Закрыть меню':'Открыть меню'} aria-expanded={open} onClick={()=>setOpen(!open)}>{open?<X/>:<Menu/>}</button></div>{open&&<button className="nav-scrim" aria-label="Закрыть меню" onClick={()=>setOpen(false)}/>}
  <aside className={`sidebar ${open?'is-open':''}`}><Brand/><div className="campus-label"><span className="campus-marker"><MapPin size={17}/></span><div>Университетский кампус<small>Екатеринбург</small></div></div>
  <nav aria-label="Основная навигация">{sections.map(section=><div className="nav-group" key={section.title}><p>{section.title}</p>{section.items.map(item=><button key={item.id} className={`nav-item ${page===item.id?'active':''}`} aria-current={page===item.id?'page':undefined} onClick={()=>{onNavigate(item.id);setOpen(false)}}><item.icon size={19}/><span>{item.title}</span>{page===item.id&&<ChevronRight size={15}/>}</button>)}</div>)}<button className={`nav-item ${page==='account'?'active':''}`} onClick={()=>{onNavigate('account');setOpen(false)}}><UserRound size={19}/><span>Мой аккаунт</span></button></nav>
  <div className="sidebar-bottom"><div className="campus-hours"><span className="status-dot"/>Кампус открыт с 08:00 до 22:00<small>Время Екатеринбурга, UTC+5</small></div><div className="profile"><span className="avatar">{user.displayName.split(' ').slice(0,2).map(s=>s[0]).join('')}</span><div><strong>{user.displayName}</strong><small>{user.role==='admin'?'Администратор':'Студент'}</small></div><button className="icon-button" aria-label="Выйти из аккаунта" title="Выйти" onClick={onLogout}><LogOut size={18}/></button></div></div></aside></>
}
export function Brand(){return <div className="brand"><span className="brand-mark"><i/><i/><i/></span><span>Campus<span className="brand-light">Flow</span><small>Пространство для твоих планов</small></span></div>}
