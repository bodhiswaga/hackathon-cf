import {useState, type FormEvent} from 'react'
import {Eye, EyeOff, LockKeyhole, Palette, ShieldCheck, UserRound} from 'lucide-react'
import {api} from '../api'
import type {User} from '../types'
import EmailSettings from './EmailSettings'
import Dialog from './Dialog'
import ThemeToggle from './ThemeToggle'

type Props = {user: User; onUser: (user: User) => void; onSignedOut: (message: string) => void}
type Feedback = {error: string; notice: string}
const emptyFeedback: Feedback = {error: '', notice: ''}

export default function AccountPage({user, onUser, onSignedOut}: Props) {
  const [name, setName] = useState(user.displayName)
  const [current, setCurrent] = useState('')
  const [password, setPassword] = useState('')
  const [repeat, setRepeat] = useState('')
  const [showPasswords, setShowPasswords] = useState(false)
  const [pending, setPending] = useState<'profile' | 'password' | 'sessions' | null>(null)
  const [profileFeedback, setProfileFeedback] = useState<Feedback>(emptyFeedback)
  const [passwordError, setPasswordError] = useState('')
  const [sessionError, setSessionError] = useState('')
  const [confirm, setConfirm] = useState(false)
  const dirty = name.trim() !== user.displayName
  const busy = pending !== null
  const passwordType = showPasswords ? 'text' : 'password'

  async function saveProfile(event: FormEvent) {
    event.preventDefault()
    if (name.trim().length < 2) {
      setProfileFeedback({error: 'Введи имя: не менее двух символов.', notice: ''})
      return
    }
    setPending('profile')
    setProfileFeedback(emptyFeedback)
    try {
      const updated = await api<User>('/auth/profile', {method: 'PATCH', body: JSON.stringify({displayName: name.trim()})})
      onUser(updated)
      setName(updated.displayName)
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
      <span className="account-avatar" aria-hidden="true">{user.displayName.trim().split(/\s+/).slice(0, 2).map(part => part[0]).join('')}</span>
      <div><h2>{user.displayName}</h2><p>@{user.login}</p></div>
      <span className="account-role">{user.role === 'admin' ? 'Администратор' : 'Студент'}</span>
    </div>

    <EmailSettings/><div className="account-sections">
      <section className="settings-section" aria-labelledby="profile-heading">
        <div className="settings-heading"><UserRound size={20} aria-hidden="true"/><div><h2 id="profile-heading">Личные данные</h2><p>Имя отображается в бронированиях.</p></div></div>
        <form className="settings-form" onSubmit={saveProfile} aria-busy={pending === 'profile'}>
          <label htmlFor="profile-name">Имя и фамилия<input id="profile-name" required minLength={2} maxLength={100} autoComplete="name" value={name} disabled={busy} onChange={event => {setName(event.target.value); setProfileFeedback(emptyFeedback)}} aria-invalid={!!profileFeedback.error} aria-describedby={profileFeedback.error ? 'profile-error' : undefined}/></label>
          <label htmlFor="profile-login">Логин<input id="profile-login" value={user.login} readOnly aria-describedby="login-hint"/></label>
          <p className="field-hint" id="login-hint">Логин используется для входа и не изменяется.</p>
          {profileFeedback.error && <p className="error" id="profile-error" role="alert">{profileFeedback.error}</p>}
          {profileFeedback.notice && <p className="notice" role="status">{profileFeedback.notice}</p>}
          <div className="settings-actions"><button className="primary" disabled={busy || !dirty}>{pending === 'profile' ? 'Сохраняем…' : 'Сохранить изменения'}</button>{dirty && <button type="button" className="secondary" disabled={busy} onClick={() => {setName(user.displayName); setProfileFeedback(emptyFeedback)}}>Отменить</button>}</div>
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
