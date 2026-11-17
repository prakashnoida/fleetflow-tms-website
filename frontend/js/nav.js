/* FleetFlow TMS — Navigation */
const VIEWS=[
 ["dashboard","▦","Dashboard"],["orders","☰","Orders"],["dispatch","⇄","Planning & Dispatch"],["tracking","◎","Live Tracking"],
 ["fleet","⛟","Drivers & Trucks"],["billing","$","Billing & Settlement"],["integrations","⚙","Integrations"]
];
function updateNav(){
 $("nav").innerHTML=VIEWS.map(([k,i,n])=>{
   let b="";
   if(k==="integrations"&&openErrors())b=`<span class="badge">${openErrors()}</span>`;
   if(k==="dispatch"){const u=loads.filter(l=>l.status==="Booked").length;if(u)b=`<span class="badge" style="background:var(--warn)">${u}</span>`;}
   return `<button class="nav ${S.view===k?"active":""}" onclick="go('${k}')"><span>${i}</span>${n}${b}</button>`;
 }).join("");
}
function go(v){S.view=v;$("side").classList.remove("open");render();window.scrollTo(0,0);}
function render(){
 updateNav();
 $("title").textContent=VIEWS.find(v=>v[0]===S.view)[2];
 ({dashboard:vDash,orders:vOrders,dispatch:vDispatch,tracking:vTracking,fleet:vFleet,billing:vBilling,integrations:vInteg})[S.view]();
}
