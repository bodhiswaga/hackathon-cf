import React from 'react'
import ReactDOM from 'react-dom/client'
import '@fontsource/golos-text/400.css'
import '@fontsource/golos-text/500.css'
import '@fontsource/golos-text/600.css'
import '@fontsource/golos-text/700.css'
import 'react-day-picker/style.css'
import './styles.css'
import App from './App'

class ErrorBoundary extends React.Component<{children:React.ReactNode},{failed:boolean}>{
  state={failed:false}
  static getDerivedStateFromError(){return {failed:true}}
  render(){return this.state.failed?<main className="fatal"><h1>Не удалось открыть страницу</h1><p>Перезагрузите приложение. Сохранённые брони останутся на месте.</p><button className="primary" onClick={()=>location.reload()}>Перезагрузить</button></main>:this.props.children}
}
ReactDOM.createRoot(document.getElementById('root')!).render(<React.StrictMode><ErrorBoundary><App/></ErrorBoundary></React.StrictMode>)
