// Calendar dates shown to the user follow the browser's local time zone.
export function localToday(now=new Date()){
 const year=now.getFullYear(),month=String(now.getMonth()+1).padStart(2,'0'),day=String(now.getDate()).padStart(2,'0');
 return `${year}-${month}-${day}`;
}
