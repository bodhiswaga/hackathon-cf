export type MailEntry={id:number;createdAt?:string;sentAt?:string}
export function mailPreview<T extends MailEntry>(items:T[],now:number){
 const stamp=items[0]?.sentAt||items[0]?.createdAt
 const expired=!stamp||!Number.isFinite(Date.parse(stamp))||now-Date.parse(stamp)>=900000
 return {expired,items:expired?[]:items.length>3?items.slice(0,1):items}
}
