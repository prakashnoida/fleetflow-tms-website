/* FleetFlow TMS — API client. All data lives in the SQLite database and is loaded from the REST API. */
const STAGES=["Booked","Planned","Dispatched","In Transit","Delivered","Invoiced"];
const HOS={drive:11,shift:14,cycle:70};
const CPM=0.62; // driver pay per mile

// In-memory copy of the database state, refreshed after every change.
let CITIES={},CUSTOMERS=[],EDI_CUSTOMERS=[],drivers=[],trucks=[],loads=[],logs=[],msgs={};

async function api(method,path,body){
 const r=await fetch(path,{method,headers:{"Content-Type":"application/json"},body:body?JSON.stringify(body):undefined});
 const j=await r.json().catch(()=>({}));
 if(r.status===401)location.href="login.html"; // session missing or expired
 if(!r.ok)throw new Error(j.error||`Request failed (${r.status})`);
 return j;
}
async function refresh(){
 const s=await api("GET","api/state");
 CITIES=s.cities;CUSTOMERS=s.customers;EDI_CUSTOMERS=s.ediCustomers;
 drivers=s.drivers;trucks=s.trucks;loads=s.loads;logs=s.logs;msgs=s.msgs;
}
/* Signed-in user */
let USER=null;
async function loadUser(){USER=await api("GET","api/auth/me");$("userName").textContent=`${USER.name} · ${USER.role}`;}
async function logout(){try{await api("POST","api/auth/logout");}catch(e){}location.href="login.html";}

function dayStr(n){return new Date(Date.now()+n*864e5).toLocaleDateString("en-US",{month:"short",day:"2-digit"});}
