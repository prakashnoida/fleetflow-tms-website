/* FleetFlow TMS — Planning & Dispatch */
function vDispatch(){
 const col=(title,st,body)=>`<div class="col"><h4>${title}<span class="muted" style="margin-left:auto">${loads.filter(l=>l.status===st).length}</span></h4>${body}</div>`;
 const card=(l,extra)=>{const d=l.driver&&drv(l.driver);return `<div class="lc ${S.selLoad===l.id?"sel":""} ${l.dispatchErr?"bad":""}" onclick="selLoad('${l.id}')"><div class="t"><span>${l.id}</span><span>${money(l.rate)}</span></div><div class="r">${l.o} → ${l.d}</div><div class="muted small">PU ${l.pu} · ${miles(l)} mi · ${l.equip}</div>${d?`<div class="small" style="margin-top:4px">👤 ${d.name} · ${d.truck}</div>`:""}${extra||""}</div>`;};
 const booked=loads.filter(l=>l.status==="Booked").map(l=>card(l)).join("")||'<div class="muted small" style="padding:8px">All loads assigned.</div>';
 const planned=loads.filter(l=>l.status==="Planned").map(l=>card(l,`<div class="row" style="margin-top:8px"><button class="btn sm p" onclick="event.stopPropagation();sendMotive('${l.id}')">Send to Motive</button><button class="btn sm" onclick="event.stopPropagation();unassign('${l.id}')">Unassign</button></div>`)).join("")||'<div class="muted small" style="padding:8px">Nothing planned.</div>';
 const disp=loads.filter(l=>l.status==="Dispatched").map(l=>card(l,l.dispatchErr?`<div class="small" style="color:var(--err);margin-top:6px">✕ Not delivered to Driver App</div><button class="btn sm" style="margin-top:6px" onclick="event.stopPropagation();sendMotive('${l.id}')">Retry</button>`:`<div class="small" style="color:var(--ok);margin-top:6px">✓ Delivered to Motive Driver App</div>`)).join("")||'<div class="muted small" style="padding:8px">None.</div>';
 const sel=S.selLoad&&ld(S.selLoad);const canAssign=sel&&sel.status==="Booked";
 const avail=drivers.slice().sort((a,b)=>busy(a.id)-busy(b.id)||(canAssign?hav(a.loc,sel.o)-hav(b.loc,sel.o):0));
 $("view").innerHTML=`
 <div class="note">Workflow: pick a <b>Booked</b> load → assign a driver (becomes <b>Planned</b>) → <b>Send to Motive</b> pushes it to the driver's app via <span class="mono">POST /v2/dispatches</span>.</div>
 <div class="grid dsp">
  <div class="kan">${col("Needs driver","Booked",booked)}${col("Preplan","Planned",planned)}${col("Sent to driver","Dispatched",disp)}</div>
  <div class="card"><h3>Driver availability <span class="sp"></span><span class="muted small">${canAssign?`for ${sel.id}`:"select a Booked load"}</span></h3>
   ${avail.map(d=>{const b=busy(d.id);const need=canAssign?miles(sel)/52:0;const dh=canAssign?Math.round(hav(d.loc,sel.o)*1.18):null;const short=canAssign&&(d.drive<need);const t=trk(d.truck);
    return `<div class="drv"><div><b>${d.name}</b> <span class="muted small">${d.truck} · ${d.status}</span><div class="muted small">📍 ${d.loc}${dh!==null?` · ${dh} mi deadhead`:""}</div>
     <div class="row small" style="margin-top:4px;gap:6px"><span class="muted">Drive</span><div class="bar ${d.drive<3?"err":d.drive<6?"warn":"ok"}" style="width:90px"><i style="width:${d.drive/HOS.drive*100}%"></i></div><span>${d.drive}h</span>${!t.motive?'<span class="pill s-Error">No Motive map</span>':""}</div>
     ${short?`<div class="small" style="color:var(--warn)">⚠ Needs ~${need.toFixed(1)}h drive; has ${d.drive}h</div>`:""}</div>
     <div>${b?'<span class="pill s-Dispatched">On load</span>':`<button class="btn sm ${canAssign?"p":""}" ${canAssign?"":"disabled"} onclick="assign('${sel?sel.id:""}','${d.id}')">Assign</button>`}</div></div>`;}).join("")}
  </div>
 </div>`;
}
function selLoad(id){S.selLoad=id;const l=ld(id);if(l.status!=="Booked"){openLoad(id);}render();}
