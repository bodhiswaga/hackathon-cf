import {useEffect,useState} from 'react'
import { Sun, Moon, Monitor } from 'lucide-react'
type Theme='light'|'dark'|'system'
export default function ThemeToggle(){
  const [theme,setTheme]=useState<Theme>(()=>(localStorage.getItem('campus-theme') as Theme)||'system')
  useEffect(()=>{const media=matchMedia('(prefers-color-scheme: dark)');const apply=()=>{document.documentElement.dataset.theme=theme==='system'?(media.matches?'dark':'light'):theme};apply();localStorage.setItem('campus-theme',theme);media.addEventListener('change',apply);return()=>media.removeEventListener('change',apply)},[theme])
  return <div className="theme-toggle" aria-label="Цветовая тема">{([{id:'light',label:'Светлая тема',icon:Sun},{id:'dark',label:'Тёмная тема',icon:Moon},{id:'system',label:'Системная тема',icon:Monitor}] as const).map(t=><button key={t.id} className={theme===t.id?'selected':''} aria-label={t.label} title={t.label} aria-pressed={theme===t.id} onClick={()=>setTheme(t.id)}><t.icon size={16}/></button>)}</div>
}
