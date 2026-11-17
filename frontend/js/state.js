/* FleetFlow TMS — State & helpers */
const S={view:"dashboard",q:"",fStatus:"All",selLoad:null,selTruck:null,fleetTab:"drivers",logSys:"All",logSt:"All",live:false,timer:null};
const $=id=>document.getElementById(id);
const money=n=>"$"+Math.round(n).toLocaleString("en-US");
const drv=id=>drivers.find(d=>d.id===id);
const trk=id=>trucks.find(t=>t.id===id);
const ld=id=>loads.find(l=>l.id===id);
const cls=s=>"s-"+s.replace(/\s/g,"");
const pill=s=>`<span class="pill ${cls(s)}">${s}</span>`;
const clock=()=>new Date().toLocaleTimeString("en-GB",{hour12:false});
function hav(a,b){const R=3959,r=x=>x*Math.PI/180,[la1,lo1]=CITIES[a],[la2,lo2]=CITIES[b];const dl=r(la2-la1),dn=r(lo2-lo1);const h=Math.sin(dl/2)**2+Math.cos(r(la1))*Math.cos(r(la2))*Math.sin(dn/2)**2;return 2*R*Math.asin(Math.sqrt(h));}
const miles=l=>Math.round(hav(l.o,l.d)*1.18);
function pos(l){const[a1,o1]=CITIES[l.o],[a2,o2]=CITIES[l.d];return[a1+(a2-a1)*l.prog,o1+(o2-o1)*l.prog];}
function proj(lat,lon){return[(lon+125)/59*1000,(49.5-lat)/25*560];}
function eta(l){const h=miles(l)*(1-l.prog)/52;const hh=Math.floor(h),mm=Math.round((h-hh)*60);return `${hh}h ${mm}m`;}
function toast(m,err){const el=document.createElement("div");el.className="toast"+(err?" err":"");el.textContent=m;$("toasts").appendChild(el);setTimeout(()=>el.remove(),3500);}
const openErrors=()=>logs.filter(x=>x.st==="Error").length;
const active=l=>["Dispatched","In Transit"].includes(l.status);
const busy=id=>loads.some(l=>l.driver===id&&["Planned","Dispatched","In Transit"].includes(l.status));
