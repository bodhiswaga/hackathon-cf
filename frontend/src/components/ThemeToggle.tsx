import {useEffect,useState} from 'react'
import { Sun, Moon, Monitor } from 'lucide-react'
type Theme='light'|'dark'|'system'
let transitionTimer:ReturnType<typeof setTimeout>|undefined
export default function ThemeToggle(){
  const [theme,setTheme]=useState<Theme>(()=>{try{const saved=localStorage.getItem('campus-theme');return saved==='light'||saved==='dark'?saved:'system'}catch{return 'system'}})
  useEffect(()=>{
    const root=document.documentElement
    const media=matchMedia('(prefers-color-scheme: dark)')
    const apply=()=>{
      const resolved=theme==='system'?(media.matches?'dark':'light'):theme
      if(root.dataset.theme!==resolved){
        root.classList.add('theme-changing')
        root.dataset.theme=resolved
        clearTimeout(transitionTimer)
        transitionTimer=setTimeout(()=>root.classList.remove('theme-changing'),360)
      }
    }
    apply()
    try{localStorage.setItem('campus-theme',theme)}catch{/* Theme still works when browser storage is disabled. */}
    const sync=()=>{try{const saved=localStorage.getItem('campus-theme');setTheme(saved==='light'||saved==='dark'?saved:'system')}catch{/* Storage may be unavailable. */}}
    // The profile and top bar share the same preference without duplicate state.
    const changed=(event:Event)=>setTheme((event as CustomEvent<Theme>).detail)
    window.addEventListener('campus-theme-change',changed)
    window.addEventListener('storage',sync)
    media.addEventListener('change',apply)
    return()=>{media.removeEventListener('change',apply);window.removeEventListener('campus-theme-change',changed);window.removeEventListener('storage',sync)}
  },[theme])
  return <div className="theme-toggle" role="group" aria-label="Цветовая тема">{([{id:'light',label:'Светлая тема',icon:Sun},{id:'dark',label:'Тёмная тема',icon:Moon},{id:'system',label:'Системная тема',icon:Monitor}] as const).map(t=><button key={t.id} className={theme===t.id?'selected':''} aria-label={t.label} title={t.label} aria-pressed={theme===t.id} onClick={()=>{setTheme(t.id);window.dispatchEvent(new CustomEvent('campus-theme-change',{detail:t.id}))}}><t.icon size={16}/></button>)}</div>
}
