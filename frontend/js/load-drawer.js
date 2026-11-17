/* FleetFlow TMS — Load drawer */
function openLoad(id){
 const l=ld(id);if(!l)return;S.selLoad=id;const d=l.driver&&drv(l.driver);const t=d&&trk(d.truck);const si=STAGES.indexOf(l.status);
 const acts=[];
 if(l.status==="Booked")acts.push(`<button class="btn p" onclick="closeAll();S.selLoad='${l.id}';go('dispatch')">Assign driver</button>`);
 if(l.status==="Planned")acts.push(`<button class="btn p" onclick="sendMotive('${l.id}');openLoad('${l.id}')">Send to Motive</button>`);
 if(active(l))acts.push(`<button class="btn" onclick="closeAll();S.selTruck='${l.id}';go('tracking')">Track on map</button>`);
 if(l.status==="Delivered")acts.push(`<button class="btn p" ${l.pod?"":"disabled"} onclick="invoice('${l.id}');openLoad('${l.id}')">Create invoice</button>`);
 $("drawer").innerHTML=`<div class="hd"><b style="font-size:16px">${l.id}</b>${pill(l.status)}<span style="flex:1"></span><button class="btn sm" onclick="closeAll()">✕</button></div>
 <div class="bd">
  <div class="tl">${STAGES.map((s,i)=>`<div class="st ${i<si?"done":i===si?"cur done":""}">${s}</div>`).join("")}</div>
  ${l.dispatchErr?`<div class="note" style="background:var(--err-soft)">⚠ Dispatch did not reach the Motive Driver App. Truck ${d.truck} is not mapped to a Motive vehicle. <a href="#" onclick="closeAll();S.fleetTab='trucks';go('fleet');return false">Fix mapping</a></div>`:""}
  <dl class="dl">
   <dt>Customer</dt><dd>${l.cust}${EDI_CUSTOMERS.includes(l.cust)?' <span class="muted small">(EDI)</span>':""}</dd>
   <dt>Pickup</dt><dd>${l.o}<div class="muted small">${l.pu}</div></dd>
   <dt>Delivery</dt><dd>${l.d}<div class="muted small">${l.del}</div></dd>
   <dt>Equipment</dt><dd>${l.equip} · ${l.weight.toLocaleString()} lb</dd>
   <dt>Miles</dt><dd>${miles(l)} practical miles</dd>
   <dt>Driver / Truck</dt><dd>${d?`${d.name} · ${d.truck}<div class="muted small">${d.phone} · Motive ${t.motive||'<span style="color:var(--err)">not mapped</span>'}</div>`:'<span class="muted">Unassigned</span>'}</dd>
   ${active(l)?`<dt>Progress</dt><dd><div class="bar" style="margin:6px 0"><i style="width:${l.prog*100}%"></i></div><span class="small muted">${Math.round(l.prog*100)}% · ETA ${eta(l)}</span></dd>`:""}
  </dl>
  <h4 style="margin:18px 0 8px">Financials</h4>
  <dl class="dl"><dt>Linehaul</dt><dd>${money(l.rate)}</dd><dt>Fuel surcharge</dt><dd>${money(miles(l)*0.48)}</dd><dt>Driver pay</dt><dd>${money(miles(l)*CPM)}</dd><dt>Margin</dt><dd><b>${money(l.rate+miles(l)*0.48-miles(l)*CPM-miles(l)*0.75)}</b> <span class="muted small">after est. fuel</span></dd>
  ${l.inv?`<dt>Invoice</dt><dd>${l.inv.no} ${pill(l.inv.st)}</dd>`:""}</dl>
  <h4 style="margin:18px 0 8px">Documents (from Motive Driver App)</h4>
  <div class="list">
   <div class="it"><div class="ico ${si>=3?"ok":"info"}">📄</div><div style="flex:1">Bill of Lading<div class="muted small">${si>=3?"Captured at pickup":"Pending pickup"}</div></div></div>
   <div class="it"><div class="ico ${l.pod?"ok":"err"}">📄</div><div style="flex:1">Proof of Delivery<div class="muted small">${l.pod?"Received":"Missing"}</div></div>${!l.pod&&l.status==="Delivered"?`<button class="btn sm" onclick="attachPod('${l.id}')">Simulate POD upload</button>`:""}</div>
  </div>
  <div class="row" style="margin-top:18px">${acts.join("")}</div>
 </div>`;
 $("drawer").classList.add("open");$("veil").classList.add("on");
}
function showModal(){$("modal").classList.add("on");$("veil").classList.add("on");}
function closeAll(){$("drawer").classList.remove("open");$("modal").classList.remove("on");$("veil").classList.remove("on");}
