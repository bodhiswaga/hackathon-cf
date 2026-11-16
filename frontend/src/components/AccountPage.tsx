import {useState, type FormEvent} from 'react'
import {Eye, EyeOff, LockKeyhole, Palette, ShieldCheck, UserRound} from 'lucide-react'
import {api} from '../api'
import type {User} from '../types'
import AvatarEditor,{Avatar} from './Avatar'
import {accounts,validateAccount,forget} from '../accounts'
import type {Auth} from '../types'
import AuthScreen from './AuthScreen'
import type {Meta} from '../types'
import EmailSettings from './EmailSettings'
import Dialog from './Dialog'
import ThemeToggle from './ThemeToggle'

type Props = {meta:Meta;onAccount:(auth:Auth)=>void;user: User; onUser: (user: User) => void; onSignedOut: (message: string) => void}
type Feedback = {error: string; notice: string}
const emptyFeedback: Feedback = {error: '', notice: ''}

export default function AccountPage({user, onUser, onSignedOut,meta,onAccount}: Props) {
  const [firstName,setFirstName]=useState(user.firstName),[lastName,setLastName]=useState(user.lastName)
  const [adding,setAdding]=useState(false),[switching,setSwitching]=useState(false),[accountError,setAccountError]=useState(''),[,setAccountRevision]=useState(0)
  const otherAccounts=accounts().filter(a=>a.user.id!==user.id)
  async function switchAccount(account:ReturnType<typeof accounts>[number]){setSwitching(true);setAccountError('');try{onAccount(await validateAccount(account))}catch(e){setAccountError((e as Error).message);setAccountRevision(v=>v+1)}finally{setSwitching(false)}}
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [showPasswords, setShowPasswords] = useState(false)
  const [pending, setPending] = useState<'profile' | 'password' | 'sessions' | null>(null)
  const [profileFeedback, setProfileFeedback] = useState<Feedback>(emptyFeedback)
  const [passwordError, setPasswordError] = useState('')
  const [sessionError, setSessionError] = useState('')
  const [confirm, setConfirm] = useState(false)
  const dirty = firstName.trim() !== user.firstName || lastName.trim() !== user.lastName
  const busy = pending !== null
  const passwordType = showPasswords ? 'text' : 'password'

  async function saveProfile(event: FormEvent) {
    event.preventDefault()
    if (!firstName.trim() || !lastName.trim()) {
      setProfileFeedback({error: 'Укажи имя и фамилию.', notice: ''})
      return
    }
    setPending('profile')
    setProfileFeedback(emptyFeedback)
    try {
      const updated = await api<User>('/auth/profile', {method: 'PATCH', body: JSON.stringify({firstName:firstName.trim(),lastName:lastName.trim()})})
      onUser(updated)
      setFirstName(updated.firstName);setLastName(updated.lastName)
      setProfileFeedback({error: '', notice: 'Изменения сохранены.'})
    } catch (error) {
      setProfileFeedback({error: (error as Error).message, notice: ''})
    } finally {
      setPending(null)
    }
  }

  async function changePassword(event: FormEvent) {
    event.preventDefault()
    setPasswordError('')
    if (password !== repeat) {
      setPasswordError('Новые пароли не совпадают.')
      return
    }
    if (current === password) {
      setPasswordError('Новый пароль должен отличаться от текущего.')
      return
    }
    setPending('password')
    try {
      await api('/auth/password', {method: 'POST', body: JSON.stringify({currentPassword: current, newPassword: password})})
      onSignedOut('Пароль изменён. Войди с новым паролем. Все прежние сессии завершены.')
    } catch (error) {
      setPasswordError((error as Error).message)
    } finally {
      setPending(null)
    }
  }

  async function revokeAll() {
    setPending('sessions')
    setSessionError('')
    try {
      await api('/auth/logout-all', {method: 'POST'})
      onSignedOut('Все сессии завершены. Войди снова, чтобы продолжить.')
    } catch (error) {
      setSessionError((error as Error).message)
    } finally {
      setPending(null)
    }
  }

  return <div className="account-page">
    <div className="page-heading"><div><div className="page-kicker">Личный кабинет</div><h1>Настройки профиля</h1><p>Личные данные, оформление и безопасность.</p></div></div>

    <div className="account-summary">
      <AvatarEditor user={user} onUser={onUser}/>
      <div><h2>{user.displayName}</h2><p>@{user.login}</p></div>
      <span className="account-role">{user.role === 'admin' ? 'Администратор' : 'Студент'}</span>
    </div>

    <section className="account-switcher" aria-label="Учетные записи">{otherAccounts.length>0&&<><h3>Другие аккаунты</h3>{otherAccounts.map(a=><div className="saved-account" key={a.user.id}><button disabled={switching} className="saved-account-select" onClick={()=>void switchAccount(a)}><Avatar user={a.user}/><span><strong>{a.user.displayName}</strong><small>@{a.user.login}</small></span><span>Переключиться</span></button><button className="icon-button" disabled={switching} aria-label={'Убрать аккаунт '+a.user.login+' из списка'} onClick={()=>{forget(a.user.id);setAccountRevision(v=>v+1)}}>×</button></div>)}</>}<button className="secondary" disabled={switching} onClick={()=>setAdding(true)}>Добавить аккаунт</button><p className="field-hint">Доступны аккаунты, в которые ты вошёл в этой вкладке. Пароли не сохраняются.</p>{accountError&&<p className="error" role="alert">{accountError}</p>}</section>
    {adding&&<Dialog title="Добавить аккаунт" wide onClose={()=>setAdding(false)}><div className="add-account-auth"><AuthScreen meta={meta} notice="Текущий аккаунт останется доступен для переключения." onAuth={value=>{setAdding(false);onAccount(value)}}/></div></Dialog>}
    <EmailSettings/><div className="account-sections">
      <section className="settings-section" aria-labelledby="profile-heading">
        <div className="settings-heading"><UserRound size={20} aria-hidden="true"/><div><h2 id="profile-heading">Личные данные</h2><p>Имя отображается в бронированиях.</p></div></div>
        <form className="settings-form" onSubmit={saveProfile} aria-busy={pending === 'profile'}>
          <div className="form-grid"><label htmlFor="profile-first">Имя<input id="profile-first" required maxLength={50} autoComplete="given-name" value={firstName} disabled={busy} onChange={e=>{setFirstName(e.target.value);setProfileFeedback(emptyFeedback)}}/></label><label htmlFor="profile-last">Фамилия<input id="profile-last" required maxLength={50} autoComplete="family-name" value={lastName} disabled={busy} onChange={e=>{setLastName(e.target.value);setProfileFeedback(emptyFeedback)}}/></label></div>
          <label htmlFor="profile-login">Логин<input id="profile-login" value={user.login} readOnly aria-describedby="login-hint"/></label>
          <p className="field-hint" id="login-hint">Логин используется для входа и не изменяется.</p>
          {profileFeedback.error && <p className="error" id="profile-error" role="alert">{profileFeedback.error}</p>}
          {profileFeedback.notice && <p className="notice" role="status">{profileFeedback.notice}</p>}
          <div className="settings-actions"><button className="primary" disabled={busy || !dirty}>{pending === 'profile' ? 'Сохраняем…' : 'Сохранить изменения'}</button>{dirty && <button type="button" className="secondary" disabled={busy} onClick={() => {setFirstName(user.firstName);setLastName(user.lastName); setProfileFeedback(emptyFeedback)}}>Отменить</button>}</div>
        </form>
      </section>

      <section className="settings-section" aria-labelledby="password-heading">
        <div className="settings-heading"><LockKeyhole size={20} aria-hidden="true"/><div><h2 id="password-heading">Пароль</h2><p>После смены потребуется войти заново на всех устройствах.</p></div></div>
        <form className="settings-form" onSubmit={changePassword} aria-busy={pending === 'password'}>
          <label htmlFor="current-password">Текущий пароль<input id="current-password" required type={passwordType} autoComplete="current-password" maxLength={128} value={current} disabled={busy} onChange={event => {setCurrent(event.target.value); setPasswordError('')}}/></label>
          <div className="password-fields">
            <label htmlFor="new-password">Новый пароль<input id="new-password" required type={passwordType} autoComplete="new-password" minLength={12} maxLength={128} value={password} disabled={busy} onChange={event => {setPassword(event.target.value); setPasswordError('')}} aria-describedby="password-hint"/></label>
            <label htmlFor="repeat-password">Повтори новый пароль<input id="repeat-password" required type={passwordType} autoComplete="new-password" minLength={12} maxLength={128} value={repeat} disabled={busy} onChange={event => {setRepeat(event.target.value); setPasswordError('')}} aria-invalid={!!passwordError} aria-describedby={passwordError ? 'password-error' : undefined}/></label>
          </div>
          <div className="password-help"><p className="field-hint" id="password-hint">От 12 до 128 символов.</p><button className="password-visibility" type="button" aria-pressed={showPasswords} onClick={() => setShowPasswords(value => !value)}>{showPasswords ? <EyeOff size={16}/> : <Eye size={16}/>} {showPasswords ? 'Скрыть пароли' : 'Показать пароли'}</button></div>
          {passwordError && <p className="error" id="password-error" role="alert">{passwordError}</p>}
          <div className="settings-actions"><button className="primary" disabled={busy || !current || !password || !repeat}>{pending === 'password' ? 'Меняем пароль…' : 'Сменить пароль'}</button></div>
        </form>
      </section>

      <section className="settings-section" aria-labelledby="appearance-heading">
        <div className="settings-heading"><Palette size={20} aria-hidden="true"/><div><h2 id="appearance-heading">Оформление</h2><p>Сохраняется в этом браузере.</p></div></div>
        <div className="settings-inline"><div><h3>Цветовая тема</h3><p className="field-hint">Светлая, тёмная или как на устройстве.</p></div><ThemeToggle/></div>
      </section>

      <section className="settings-section" aria-labelledby="sessions-heading">
        <div className="settings-heading"><ShieldCheck size={20} aria-hidden="true"/><div><h2 id="sessions-heading">Вход и сессии</h2><p>Управление доступом к аккаунту.</p></div></div>
        <div className="settings-form"><div><h3>Выйти на всех устройствах</h3><p className="field-hint">Завершит все входы, включая текущий. Для возвращения понадобятся логин и пароль.</p></div><div className="settings-actions"><button className="secondary" disabled={busy} onClick={() => {setSessionError(''); setConfirm(true)}}>Завершить все сессии</button></div></div>
      </section>
    </div>

    {confirm && <Dialog title="Завершить все сессии?" onClose={() => {if (!busy) setConfirm(false)}}><div className="confirm-body"><p>Ты выйдешь из аккаунта на всех устройствах, включая это. Несохранённые изменения профиля будут потеряны.</p>{sessionError && <p className="error" role="alert">{sessionError}</p>}<div className="actions"><button className="secondary" disabled={busy} onClick={() => setConfirm(false)}>Остаться</button><button className="danger" disabled={busy} onClick={revokeAll}>{pending === 'sessions' ? 'Завершаем…' : 'Выйти везде'}</button></div></div></Dialog>}
  </div>
}
