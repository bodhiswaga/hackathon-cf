export function readAvatarFile(file:Blob):Promise<string>{
 return new Promise((resolve,reject)=>{
  const reader=new FileReader()
  reader.onload=()=>typeof reader.result==='string'?resolve(reader.result):reject(new Error('Не удалось прочитать файл. Выбери фото ещё раз.'))
  reader.onerror=()=>reject(new Error('Не удалось прочитать файл. Выбери фото ещё раз.'))
  reader.onabort=()=>reject(new Error('Чтение файла отменено. Выбери фото ещё раз.'))
  reader.readAsDataURL(file)
 })
}
