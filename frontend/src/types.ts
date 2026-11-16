export type User = {id:number; login:string; role:'student'|'admin'; displayName:string}
export type Interval = {startTime:string; endTime:string}
export type Room = {id:number; name:string; building:string; floor:number; capacity:number; equipment:string[]; description:string; active:boolean; busySlots?:Interval[]; freeSlots?:Interval[]}
export type Booking = Interval & {id:number; held?:boolean; checkedIn?:boolean;attendance?:{state:string;deadline:string;reason?:string};warnings?:string[]; roomId:number; userId:number; date:string; status:'active'|'cancelled'; comment:string; room:Room; user:User}
export type Meta = {timezone:string; today:string; now:string; opensAt:string; closesAt:string; buildings:string[]; equipment:Record<string,string>;demo:boolean;registrationMode:'open'|'invite'|'closed'}
export type Auth = {accessToken:string; user:User}
export type Stats = {rooms:{id:number;name:string;hours:number}[];attendance:{checkedIn:number;unconfirmedPast:number};heldCount:number;hourly:{date:string;building:string;hour:string;occupancy:number}[];rows:{date:string;building:string;bookings:number;occupiedMinutes:number;availableMinutes:number;occupancy:number}[];roomCount:number;bookingCount:number;occupiedHours:number}
