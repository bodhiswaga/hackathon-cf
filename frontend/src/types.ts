export type User = {id:number; login:string; role:'student'|'admin'; displayName:string}
export type Interval = {startTime:string; endTime:string}
export type Room = {id:number; name:string; building:string; floor:number; capacity:number; equipment:string[]; description:string; active:boolean; busySlots?:Interval[]; freeSlots?:Interval[]}
export type Booking = Interval & {id:number; roomId:number; userId:number; date:string; status:'active'|'cancelled'; comment:string; room:Room; user:User}
export type Meta = {timezone:string; today:string; now:string; opensAt:string; closesAt:string; buildings:string[]; equipment:Record<string,string>;demo:boolean;registrationMode:'open'|'invite'|'closed'}
export type Auth = {accessToken:string; user:User}
export type Stats = {rows:{date:string;building:string;bookings:number;occupiedMinutes:number;availableMinutes:number;occupancy:number}[];roomCount:number;bookingCount:number;occupiedHours:number}
