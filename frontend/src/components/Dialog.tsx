import {useEffect,useRef,type ReactNode} from 'react'
import {X} from 'lucide-react'
export default function Dialog({title,onClose,children,wide=false}:{title:string;onClose:()=>void;children:ReactNode;wide?:boolean}){
 const ref=useRef<HTMLDialogElement>(null)
 useEffect(()=>{const element=ref.current;const previous=document.activeElement as HTMLElement|null;element?.showModal();return()=>{element?.close();previous?.focus()}},[])
 return <dialog ref={ref} className={`dialog ${wide?'wide':''}`} aria-label={title} onCancel={e=>{e.preventDefault();onClose()}} onClick={e=>{if(e.target===e.currentTarget){const r=e.currentTarget.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)onClose()}}}><header className="dialog-header"><h2>{title}</h2><button className="icon-button" aria-label="Закрыть окно" onClick={onClose}><X size={20}/></button></header>{children}</dialog>
}
