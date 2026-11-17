/* FleetFlow TMS — Orders */
function vOrders(){
 $("view").innerHTML=`
 <div class="card">
  <div class="row" style="margin-bottom:12px">
   <input id="q" placeholder="Search load, customer, city…" value="${S.q}" oninput="S.q=this.value;ordTable()" style="flex:1;min-width:200px">
   <select onchange="S.fStatus=this.value;ordTable()">${["All",...STAGES].map(s=>`<option ${S.fStatus===s?"selected":""}>${s}</option>`).join("")}</select>
   <button class="btn" onclick="ediImport()">⇣ Simulate EDI 204</button>
   <button class="btn p" onclick="newOrder()">+ New order</button>
  </div>
  <div class="tw" id="ordT"></div>
 </div>`;
 ordTable();
}
function ordTable(){
 const q=S.q.toLowerCase();
 const rows=loads.filter(l=>(S.fStatus==="All"||l.status===S.fStatus)&&(!q||[l.id,l.cust,l.o,l.d].join(" ").toLowerCase().includes(q)));
 $("ordT").innerHTML=`<table><thead><tr><th>Load #</th><th>Customer</th><th>Origin → Destination</th><th>Pickup</th><th>Delivery</th><th>Equipment</th><th>Miles</th><th>Rate</th><th>Driver</th><th>Status</th></tr></thead><tbody>
 ${rows.map(l=>`<tr class="click" onclick="openLoad('${l.id}')"><td><b>${l.id}</b></td><td>${l.cust}</td><td>${l.o} → ${l.d}</td><td style="white-space:nowrap">${l.pu}</td><td style="white-space:nowrap">${l.del}</td><td>${l.equip}</td><td>${miles(l)}</td><td>${money(l.rate)}</td><td>${l.driver?drv(l.driver).name:'<span class="muted">—</span>'}</td><td>${pill(l.status)}${l.late?' <span class="pill s-Error">Late</span>':""}</td></tr>`).join("")||'<tr><td colspan="10" class="muted">No loads match.</td></tr>'}
 </tbody></table>`;
}
function newOrder(){
 const opt=a=>a.map(x=>`<option>${x}</option>`).join("");const c=Object.keys(CITIES);
 $("modal").innerHTML=`<div class="hd">New order</div><div class="bd">
  <label class="fld full">Customer<select id="nCust">${opt(CUSTOMERS)}</select></label>
  <label class="fld">Origin<select id="nO">${opt(c)}</select></label>
  <label class="fld">Destination<select id="nD">${opt(c.slice(1).concat(c[0]))}</select></label>
  <label class="fld">Pickup<input id="nPu" value="${dayStr(1)}, 08:00"></label>
  <label class="fld">Delivery<input id="nDel" value="${dayStr(2)}, 12:00"></label>
  <label class="fld">Equipment<select id="nEq">${opt(["53' Dry Van","53' Reefer","48' Flatbed","53' Hopper"])}</select></label>
  <label class="fld">Weight (lb)<input id="nW" type="number" value="40000"></label>
  <label class="fld">Linehaul rate ($)<input id="nR" type="number" value="1800"></label>
  <div class="fld" style="justify-content:flex-end"><span id="nMi" class="muted"></span></div>
 </div><div class="ft"><button class="btn" onclick="closeAll()">Cancel</button><button class="btn p" onclick="saveOrder()">Create order</button></div>`;
 const upd=()=>{const o=$("nO").value,d=$("nD").value;$("nMi").textContent=o===d?"Origin and destination must differ":`≈ ${Math.round(hav(o,d)*1.18)} practical miles`;};
 $("nO").onchange=upd;$("nD").onchange=upd;upd();
 showModal();
}
