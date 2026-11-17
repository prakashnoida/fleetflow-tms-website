/* FleetFlow TMS — Fleet */
function vFleet(){
 const tab=(k,n)=>`<button class="tab ${S.fleetTab===k?"on":""}" onclick="S.fleetTab='${k}';render()">${n}</button>`;
 let body;
 if(S.fleetTab==="drivers"){
  body=`<table><thead><tr><th>Driver</th><th>Status</th><th>Location</th><th>Truck</th><th style="min-width:200px">HOS remaining (Motive ELD)</th><th>Current load</th></tr></thead><tbody>
  ${drivers.map(d=>{const l=loads.find(x=>x.driver===d.id&&["Planned","Dispatched","In Transit"].includes(x.status));return `<tr><td><b>${d.name}</b><div class="muted small">${d.id} · ${d.phone}</div></td><td>${d.status}</td><td>${d.loc}</td><td>${d.truck}</td><td>${hosBars(d)}</td><td>${l?`<a href="#" onclick="openLoad('${l.id}');return false">${l.id}</a>`:'<span class="muted">—</span>'}</td></tr>`;}).join("")}</tbody></table>`;
 }else{
  body=`<table><thead><tr><th>Truck</th><th>Unit</th><th>Motive vehicle ID</th><th>Odometer</th><th>Fuel</th><th>Fault codes</th><th>Driver</th></tr></thead><tbody>
  ${trucks.map(t=>{const d=drivers.find(x=>x.truck===t.id);return `<tr><td><b>${t.id}</b></td><td>${t.unit}</td><td>${t.motive?`<span class="mono">${t.motive}</span> <span class="pill s-Success">Mapped</span>`:`<span class="pill s-Error">Not mapped</span> <button class="btn sm" onclick="mapTruck('${t.id}')">Map to Motive</button>`}</td><td>${t.odo.toLocaleString()} mi</td><td><div class="bar ${t.fuel<25?"err":t.fuel<45?"warn":"ok"}" style="width:70px;display:inline-block;vertical-align:middle"><i style="width:${t.fuel}%"></i></div> ${t.fuel}%</td><td>${t.fault?`<span style="color:var(--warn)">${t.fault}</span>`:'<span class="muted">None</span>'}</td><td>${d?d.name:"—"}</td></tr>`;}).join("")}</tbody></table>`;
 }
 $("view").innerHTML=`<div class="card"><div class="tabs">${tab("drivers","Drivers")}${tab("trucks","Trucks & Motive mapping")}</div><div class="tw">${body}</div></div>`;
}
