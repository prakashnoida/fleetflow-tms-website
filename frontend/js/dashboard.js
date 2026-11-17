/* FleetFlow TMS — Dashboard */
function vDash(){
 const act=loads.filter(l=>["Planned","Dispatched","In Transit"].includes(l.status)).length;
 const tr=loads.filter(l=>l.status==="In Transit");
 const unas=loads.filter(l=>l.status==="Booked").length;
 const done=loads.filter(l=>["Delivered","Invoiced"].includes(l.status));
 const ontime=Math.round(100*(loads.filter(l=>l.status!=="Booked"&&!l.late).length)/Math.max(1,loads.filter(l=>l.status!=="Booked").length));
 const rev=loads.filter(l=>l.status!=="Booked").reduce((a,l)=>a+l.rate,0);
 const ex=[];
 loads.filter(l=>l.late&&l.status==="In Transit").forEach(l=>ex.push(["warn","⏱",`${l.id} running late`,`${l.o} → ${l.d} · ETA ${eta(l)}`,`openLoad('${l.id}')`]));
 loads.filter(l=>l.status==="Booked").forEach(l=>ex.push(["warn","!",`${l.id} has no driver`,`Pickup ${l.pu} · ${l.o}`,`go('dispatch')`]));
 drivers.filter(d=>d.drive<2.5&&busy(d.id)).forEach(d=>ex.push(["err","⌛",`${d.name}: ${d.drive}h drive time left`,`HOS – plan a relay or rest stop`,`go('fleet')`]));
 loads.filter(l=>l.status==="Delivered"&&!l.pod).forEach(l=>ex.push(["err","📄",`${l.id} delivered without POD`,`Billing blocked`,`openLoad('${l.id}')`]));
 logs.filter(x=>x.st==="Error").forEach(x=>ex.push(["err","⚙",`${x.sys}: ${x.type} failed`,x.msg,`go('integrations')`]));
 const counts=STAGES.map(s=>[s,loads.filter(l=>l.status===s).length]);const mx=Math.max(...counts.map(c=>c[1]),1);
 $("view").innerHTML=`
 <div class="grid k4">
  ${kpi("Active loads",act,`${tr.length} in transit`)}
  ${kpi("Needs a driver",unas,"Booked, not yet planned")}
  ${kpi("On-time %",ontime+"%","This week")}
  ${kpi("Revenue (week)",money(rev),`${done.length} loads delivered`)}
  ${kpi("Integration errors",openErrors(),"Motive · EDI · ERP")}
 </div>
 <div class="grid c2" style="margin-top:16px">
  <div class="card"><h3>Exceptions <span class="pill s-Error">${ex.length}</span></h3>
   <div class="list">${ex.map(e=>`<div class="it" style="cursor:pointer" onclick="${e[4]}"><div class="ico ${e[0]}">${e[1]}</div><div><b>${e[2]}</b><div class="muted small">${e[3]}</div></div></div>`).join("")||'<div class="muted">No exceptions 🎉</div>'}</div>
  </div>
  <div class="grid" style="align-content:start">
   <div class="card"><h3>Loads by status</h3>${counts.map(([s,c])=>`<div class="hb"><span>${s}</span><div class="bar"><i style="width:${c/mx*100}%"></i></div><b>${c}</b></div>`).join("")}</div>
   <div class="card"><h3>Recent OBC / integration activity<span class="sp"></span><button class="btn sm" onclick="go('integrations')">View all</button></h3>
    <div class="list">${logs.slice(0,5).map(x=>`<div class="it"><div class="ico ${x.st==="Error"?"err":"ok"}">${x.dir==="IN"?"↓":"↑"}</div><div style="min-width:0"><b>${x.sys} · ${x.type}</b> <span class="muted small">${x.t}</span><div class="muted small">${x.msg}</div></div></div>`).join("")}</div>
   </div>
  </div>
 </div>`;
}
const kpi=(l,v,s)=>`<div class="card kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`;
