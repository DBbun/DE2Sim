"""Standalone Phase 5A simulation viewer."""

from __future__ import annotations

import copy
import json
from typing import Any


VIEWER_SCHEMA_VERSION = "de2sim.simulation_viewer.v1"
MAX_TEXT = 700


class SimulationViewerError(Exception):
    """Controlled simulation viewer generation failure."""


def build_simulation_viewer_data(package: dict[str, Any]) -> dict[str, Any]:
    data = copy.deepcopy(package)
    return {
        "schema_version": VIEWER_SCHEMA_VERSION,
        "simulation_run_id": data["simulation_run_id"],
        "title": data["asot_facts"]["title"],
        "approved_behavior_id": data["asot_facts"]["approved_behavior_id"],
        "scenario": data["scenario"],
        "asot_links": {
            "requirements": data["asot_facts"]["requirement_ids"],
            "parameters": data["asot_facts"]["parameter_ids"],
            "behaviors": {
                "approved": data["asot_facts"]["approved_behavior_id"],
                "source_return_to_base": data["asot_facts"]["source_return_to_base_behavior_id"],
            },
            "provenance_ids": data["asot_facts"]["provenance_ids"],
        },
        "telemetry": data["telemetry"],
        "events": data["events"],
        "simulation_status": data["simulation_status"],
        "requirements_evaluation": data["requirements_evaluation"],
        "fidelity_comparison": data["fidelity_comparison"],
        "battery_threshold_percent": data["asot_facts"]["battery_threshold_percent"],
        "limitations": [_limit_text(item) for item in data["limitations"]],
        "playback_seconds_per_simulation_second": data["scenario"]["playback_seconds_per_simulation_second"]["value"],
    }


def render_simulation_viewer_html(data: dict[str, Any]) -> str:
    text = json.dumps(data, indent=2, sort_keys=True, ensure_ascii=False).replace("</", "<\\/")
    return _HTML.replace("__SIMULATION_DATA_JSON__", text)


def _limit_text(value: Any) -> str:
    text = "" if value is None else str(value)
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "\n[truncated]"


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>DE2Sim Simulation Viewer</title>
<style>
:root{color-scheme:light;--ink:#1f2933;--muted:#586474;--line:#c8d1dc;--panel:#f7f9fb;--ok:#177245;--bad:#a73737;--warn:#8a6500;--blue:#245c9c;--teal:#08747c;--gold:#9a6b00;--red:#b23b31}
*{box-sizing:border-box}body{margin:0;height:100vh;display:grid;grid-template-rows:auto 1fr;background:#ffffff;color:var(--ink);font-family:Arial,Helvetica,sans-serif;font-size:14px;letter-spacing:0}header{padding:12px 16px;border-bottom:1px solid var(--line);background:#f2f5f8}h1{margin:0 0 5px 0;font-size:20px}h2{margin:0 0 8px 0;font-size:15px}.meta{display:flex;gap:8px;flex-wrap:wrap;color:var(--muted)}.meta span,.pill,.badge{border:1px solid var(--line);background:#fff;padding:3px 7px;border-radius:6px}.badge{display:inline-block;margin-top:4px;color:var(--muted);font-size:12px}.layout{min-height:0;display:grid;grid-template-columns:minmax(340px,22%) minmax(560px,1fr) minmax(400px,26%)}.side,.details{min-height:0;overflow:auto;padding:14px;border-right:1px solid var(--line);background:var(--panel)}.details{border-right:0;border-left:1px solid var(--line)}main{min-height:0;display:grid;grid-template-rows:auto 1fr 240px}.toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:10px;border-bottom:1px solid var(--line)}button,select,input[type=range],input[type=number]{font:inherit}button{border:1px solid var(--line);background:#fff;border-radius:6px;padding:5px 9px;cursor:pointer}.mapwrap{min-height:0;position:relative;background:#fff}svg{display:block;width:100%;height:100%;min-height:280px}.charts{display:grid;grid-template-columns:1fr 1fr;gap:10px;padding:10px;border-top:1px solid var(--line);background:#fbfcfd}.chart{border:1px solid var(--line);background:#fff;border-radius:8px;min-width:0}.section{margin-bottom:14px}.field{padding:8px;margin:7px 0;border:1px solid var(--line);border-radius:8px;background:#fff}.field-label{font-weight:bold}.machine{color:var(--muted);font-size:12px;overflow-wrap:anywhere}.value{margin-top:4px;overflow-wrap:anywhere}.explain{margin-top:5px;color:var(--muted);line-height:1.35;overflow-wrap:anywhere}.kv{display:block;margin:8px 0}.kv dt{font-weight:bold}.kv dd{margin:3px 0 0 0;overflow-wrap:anywhere}.status-card{border:2px solid var(--line);border-radius:8px;background:#fff;padding:10px}.status-card.pass{border-color:var(--ok)}.status-card.fail{border-color:var(--bad)}.state-seq{display:flex;gap:5px;flex-wrap:wrap}.state-seq span{padding:4px 6px;border-radius:6px;background:#fff;border:1px solid var(--line)}.state-seq .active{background:#dfefff;border-color:var(--blue)}.ok{color:var(--ok)}.fail{color:var(--bad)}.warn{color:var(--warn)}table{width:100%;border-collapse:collapse;background:#fff}td,th{border:1px solid var(--line);padding:5px;text-align:left;vertical-align:top;overflow-wrap:anywhere}ol{padding-left:18px}.path-low{fill:none;stroke:var(--blue);stroke-width:3}.path-high{fill:none;stroke:var(--teal);stroke-width:3;stroke-dasharray:8 5}.home{fill:var(--ok)}.waypoint{fill:var(--gold)}.uas{fill:var(--red);stroke:#fff;stroke-width:2}.grid{stroke:#e3e8ee;stroke-width:1}.axis{stroke:#667382;stroke-width:1}.line-battery{fill:none;stroke:var(--gold);stroke-width:2}.line-speed{fill:none;stroke:var(--blue);stroke-width:2}.threshold{stroke:var(--bad);stroke-width:1.5;stroke-dasharray:5 4}.current-marker{stroke:#111827;stroke-width:1.5}.eventitem{border-bottom:1px solid var(--line);padding:6px 0}.eventitem.important{border-left:4px solid var(--blue);padding-left:7px}.eventitem.depleted{border-left-color:var(--bad)}details summary{cursor:pointer}.legend text,.maplabel{font-size:12px;paint-order:stroke;stroke:#fff;stroke-width:3px;stroke-linejoin:round}
</style>
</head>
<body>
<header><h1 id="title"></h1><div class="meta" id="meta"></div></header>
<div class="layout">
<aside class="side">
  <section class="section"><h2>Scenario Assumptions</h2><dl id="scenario"></dl></section>
  <section class="section"><h2>State Sequence</h2><div class="state-seq" id="states"></div></section>
  <section class="section"><h2>Simulation Status</h2><div id="status"></div></section>
  <section class="section"><h2>Requirement Status</h2><div id="requirements"></div></section>
  <section class="section"><h2>Limitations</h2><ol id="limitations"></ol></section>
</aside>
<main>
  <div class="toolbar">
    <select id="fidelity"><option value="low">Low fidelity</option><option value="high">High fidelity</option><option value="comparison">Side-by-side comparison</option></select>
    <button id="play" type="button">Play</button><button id="pause" type="button">Pause</button><button id="reset" type="button">Reset</button>
    <label>Speed <select id="speed"><option value="0.5">0.5x</option><option value="1" selected>1x</option><option value="2">2x</option><option value="4">4x</option><option value="8">8x</option></select></label>
    <label>Time <input id="scrub" type="range" min="0" max="1" step="1" value="0"></label>
  </div>
  <div class="mapwrap"><svg id="map" role="img" aria-label="mission map"></svg></div>
  <div class="charts"><svg class="chart" id="batteryChart" role="img" aria-label="battery versus time chart"></svg><svg class="chart" id="speedChart" role="img" aria-label="speed versus time chart"></svg></div>
</main>
<aside class="details">
  <section class="section"><h2>Current Telemetry</h2><dl id="telemetry"></dl></section>
  <section class="section"><h2>Event Timeline</h2><div id="events"></div></section>
  <section class="section"><h2>Fidelity Comparison</h2><div id="comparison"></div></section>
  <section class="section"><h2>Linked ASOT Items</h2><dl id="links"></dl></section>
</aside>
</div>
<script id="simulation-data" type="application/json">__SIMULATION_DATA_JSON__</script>
<script>
"use strict";
const data=JSON.parse(document.getElementById("simulation-data").textContent);
const state={fidelity:"low",index:0,playing:false,timer:null};
const ns="http://www.w3.org/2000/svg";
function txt(el,value){el.textContent=value==null?"":String(value)}
function clear(el){while(el.firstChild)el.removeChild(el.firstChild)}
function child(tag,parent,attrs){const el=document.createElementNS(ns,tag);for(const k in attrs||{})el.setAttribute(k,attrs[k]);parent.appendChild(el);return el}
function rows(){return state.fidelity==="high"?data.telemetry.high:data.telemetry.low}
function row(){const r=rows();return r[Math.min(state.index,r.length-1)]}
function fidelityKey(){return state.fidelity==="high"?"high":"low"}
function labelize(name){return String(name).split("_").map(part=>part?part.charAt(0).toUpperCase()+part.slice(1):part).join(" ").replace("Mps2","m/s^2").replace("Mps","m/s")}
function fmt(value,unit){return (value==null?"not available":String(value))+(unit?" "+unit:"")}
function bounds(){const all=data.telemetry.low.concat(data.telemetry.high);let minX=Infinity,minY=Infinity,maxX=-Infinity,maxY=-Infinity;all.forEach(p=>{minX=Math.min(minX,p.x_m);minY=Math.min(minY,p.y_m);maxX=Math.max(maxX,p.x_m);maxY=Math.max(maxY,p.y_m)});const pad=500;return {minX:minX-pad,minY:minY-pad,maxX:maxX+pad,maxY:maxY+pad}}
function sx(x,b,w){return 40+(x-b.minX)/Math.max(1,b.maxX-b.minX)*(w-80)}
function sy(y,b,h){return h-40-(y-b.minY)/Math.max(1,b.maxY-b.minY)*(h-80)}
function pathFor(items,b,w,h){return items.map((p,i)=>(i?"L":"M")+sx(p.x_m,b,w).toFixed(2)+" "+sy(p.y_m,b,h).toFixed(2)).join(" ")}
function renderHeader(){txt(document.getElementById("title"),(data.title||"DE2Sim")+" Simulation Viewer");const meta=document.getElementById("meta");clear(meta);["run "+data.simulation_run_id,"approved behavior "+data.approved_behavior_id,"preflight -> mission_flight -> return_to_base -> landed"].forEach(v=>{const s=document.createElement("span");txt(s,v);meta.appendChild(s)})}
function renderScenario(){const dl=document.getElementById("scenario");clear(dl);Object.keys(data.scenario).sort().forEach(k=>{const v=data.scenario[k];const card=document.createElement("div");card.className="field";card.title=k;const label=document.createElement("div");label.className="field-label";txt(label,labelize(k));const machine=document.createElement("div");machine.className="machine";txt(machine,k);const value=document.createElement("div");value.className="value";txt(value,fmt(v.value,v.unit));const badge=document.createElement("span");badge.className="badge";txt(badge,v.source_classification);const explain=document.createElement("div");explain.className="explain";txt(explain,v.explanation);card.appendChild(label);card.appendChild(machine);card.appendChild(value);card.appendChild(badge);card.appendChild(explain);dl.appendChild(card)})}
function renderMap(){const svg=document.getElementById("map");clear(svg);const w=svg.clientWidth||760,h=svg.clientHeight||420,b=bounds();svg.setAttribute("viewBox","0 0 "+w+" "+h);for(let i=0;i<8;i++){child("line",svg,{x1:55+i*(w-100)/7,y1:38,x2:55+i*(w-100)/7,y2:h-50,class:"grid"});child("line",svg,{x1:55,y1:38+i*(h-92)/7,x2:w-45,y2:38+i*(h-92)/7,class:"grid"})}const low=data.telemetry.low,high=data.telemetry.high;if(state.fidelity==="comparison"){child("path",svg,{d:pathFor(low,b,w,h),class:"path-low"});child("path",svg,{d:pathFor(high,b,w,h),class:"path-high"})}else{const visible=rows().slice(0,Math.max(1,state.index+1));child("path",svg,{d:pathFor(visible,b,w,h),class:state.fidelity==="low"?"path-low":"path-high"})}const sc=data.scenario;const hx=sx(sc.home_x_m.value,b,w),hy=sy(sc.home_y_m.value,b,h),wx=sx(sc.mission_waypoint_x_m.value,b,w),wy=sy(sc.mission_waypoint_y_m.value,b,h);child("circle",svg,{cx:hx,cy:hy,r:8,class:"home"});child("circle",svg,{cx:wx,cy:wy,r:8,class:"waypoint"});let t=child("text",svg,{x:hx+12,y:hy-10,class:"maplabel"});txt(t,"Home");t=child("text",svg,{x:Math.max(60,wx-125),y:wy-12,class:"maplabel"});txt(t,"Mission Waypoint");const p=row();const ux=sx(p.x_m,b,w),uy=sy(p.y_m,b,h);child("circle",svg,{cx:ux,cy:uy,r:9,class:"uas"});t=child("text",svg,{x:ux+12,y:uy+4,class:"maplabel"});txt(t,"UAS");t=child("text",svg,{x:18,y:24,class:"maplabel"});txt(t,"Current state: "+p.state);const legend=child("g",svg,{class:"legend"});child("line",legend,{x1:w-190,y1:20,x2:w-150,y2:20,class:"path-low"});t=child("text",legend,{x:w-144,y:24});txt(t,"Low path");child("line",legend,{x1:w-190,y1:42,x2:w-150,y2:42,class:"path-high"});t=child("text",legend,{x:w-144,y:46});txt(t,"High path");child("circle",legend,{cx:w-185,cy:66,r:6,class:"uas"});t=child("text",legend,{x:w-172,y:70});txt(t,"Current UAS")}
function renderStates(){const c=document.getElementById("states");clear(c);["preflight","mission_flight","return_to_base","landed"].forEach(s=>{const el=document.createElement("span");if(row().state===s)el.className="active";txt(el,s);c.appendChild(el)})}
function renderTelemetry(){const dl=document.getElementById("telemetry");clear(dl);const p=row();const units={time_s:"s",battery_state_percent:"percent",battery_energy_wh:"Wh",ground_speed_mps:"m/s",commanded_speed_mps:"m/s",distance_to_home_m:"m",distance_to_waypoint_m:"m"};["time_s","state","battery_state_percent","battery_energy_wh","ground_speed_mps","commanded_speed_mps","distance_to_home_m","distance_to_waypoint_m","event"].forEach(k=>{const div=document.createElement("div");div.className="kv";div.title=k;const dt=document.createElement("dt"),dd=document.createElement("dd");txt(dt,labelize(k));txt(dd,fmt(p[k],units[k]||""));div.appendChild(dt);div.appendChild(dd);dl.appendChild(div)})}
function renderStatus(){const c=document.getElementById("status");clear(c);const status=data.simulation_status[fidelityKey()];const card=document.createElement("div");card.className="status-card "+(status.scenario_feasibility_status==="pass"?"pass":"fail");[["Mission completed",status.mission_completed],["Terminal reason",status.terminal_reason],["Battery reserve at landing",status.battery_reserve_at_landing_percent==null?"not landed":status.battery_reserve_at_landing_percent+" percent"],["Battery depleted before landing",status.battery_depleted_before_landing],["Scenario feasibility",status.scenario_feasibility_status],["Feasibility explanation",status.scenario_feasibility_explanation]].forEach(([k,v])=>{const dl=document.createElement("dl");dl.className="kv";const dt=document.createElement("dt"),dd=document.createElement("dd");txt(dt,k);txt(dd,v);dl.appendChild(dt);dl.appendChild(dd);card.appendChild(dl)});c.appendChild(card)}
function renderRequirements(){const c=document.getElementById("requirements");clear(c);const req=data.requirements_evaluation[state.fidelity==="high"?"high":"low"];["low_battery_return","maximum_speed"].forEach(k=>{const p=document.createElement("div");p.className=req[k].status==="pass"?"ok":"fail";txt(p,k+": "+req[k].status);c.appendChild(p)})}
function renderEvents(){const c=document.getElementById("events");clear(c);const ev=data.events[fidelityKey()];const important=new Set(["battery_threshold_reached","return_to_base_invoked","home_position_reached","landed","battery_depleted"]);ev.forEach(e=>{const wrap=document.createElement("details");wrap.className="eventitem"+(important.has(e.event_type)?" important":"")+(e.event_type==="battery_depleted"?" depleted":"");const s=document.createElement("summary");txt(s,e.time_s+"s - "+labelize(e.event_type)+" - "+e.state_before+" -> "+e.state_after);wrap.appendChild(s);const d=document.createElement("div");txt(d,"trigger: "+e.trigger+" | guard: "+e.guard+" | action: "+e.action);wrap.appendChild(d);const ids=document.createElement("div");ids.className="machine";txt(ids,"requirements "+e.related_requirement_ids.join(", ")+" | parameters "+e.related_parameter_ids.join(", "));wrap.appendChild(ids);c.appendChild(wrap)})}
function chart(svgId,key,klass){const svg=document.getElementById(svgId);clear(svg);const w=svg.clientWidth||460,h=svg.clientHeight||210;svg.setAttribute("viewBox","0 0 "+w+" "+h);const rs=rows();const maxT=Math.max(...rs.map(r=>r.time_s));const maxV=Math.max(...rs.map(r=>r[key]),key==="battery_state_percent"?100:1);const left=52,right=18,top=34,bottom=38;child("line",svg,{x1:left,y1:h-bottom,x2:w-right,y2:h-bottom,class:"axis"});child("line",svg,{x1:left,y1:top,x2:left,y2:h-bottom,class:"axis"});let title=child("text",svg,{x:left,y:20});txt(title,labelize(key)+(key.includes("speed")?" (m/s)":" (percent)"));let unit=child("text",svg,{x:8,y:top+8});txt(unit,key.includes("speed")?"m/s":"%");const xFor=t=>left+t/Math.max(1,maxT)*(w-left-right);const yFor=v=>h-bottom-v/maxV*(h-top-bottom);if(key==="battery_state_percent"){const ty=yFor(data.battery_threshold_percent);child("line",svg,{x1:left,y1:ty,x2:w-right,y2:ty,class:"threshold"});const tl=child("text",svg,{x:left+6,y:ty-5});txt(tl,"threshold "+data.battery_threshold_percent+"%")}const d=rs.map((r,i)=>(i?"L":"M")+xFor(r.time_s).toFixed(2)+" "+yFor(r[key]).toFixed(2)).join(" ");child("path",svg,{d:d,class:klass});const markerX=xFor(row().time_s);child("line",svg,{x1:markerX,y1:top,x2:markerX,y2:h-bottom,class:"current-marker"});const ct=child("text",svg,{x:Math.min(w-90,markerX+5),y:h-12});txt(ct,"t="+row().time_s+"s")}
function renderComparison(){const c=document.getElementById("comparison");clear(c);const table=document.createElement("table");const head=document.createElement("tr");["metric","low","high"].forEach(x=>{const th=document.createElement("th");txt(th,x);head.appendChild(th)});table.appendChild(head);Object.keys(data.fidelity_comparison.low).forEach(k=>{const tr=document.createElement("tr");[k,data.fidelity_comparison.low[k],data.fidelity_comparison.high[k]].forEach(x=>{const td=document.createElement("td");txt(td,x);tr.appendChild(td)});table.appendChild(tr)});c.appendChild(table);const p=document.createElement("p");txt(p,data.fidelity_comparison.explanation);c.appendChild(p)}
function renderLinks(){const dl=document.getElementById("links");clear(dl);Object.keys(data.asot_links).forEach(k=>{const div=document.createElement("div");div.className="kv";const dt=document.createElement("dt"),dd=document.createElement("dd");txt(dt,k);txt(dd,JSON.stringify(data.asot_links[k]));div.appendChild(dt);div.appendChild(dd);dl.appendChild(div)})}
function renderLimitations(){const ol=document.getElementById("limitations");clear(ol);data.limitations.forEach(x=>{const li=document.createElement("li");txt(li,x);ol.appendChild(li)})}
function renderAll(){document.getElementById("scrub").max=String(rows().length-1);document.getElementById("scrub").value=String(state.index);renderHeader();renderScenario();renderMap();renderStates();renderStatus();renderTelemetry();renderRequirements();renderEvents();chart("batteryChart","battery_state_percent","line-battery");chart("speedChart","ground_speed_mps","line-speed");renderComparison();renderLinks();renderLimitations()}
function pause(){state.playing=false;if(state.timer){clearInterval(state.timer);state.timer=null}}
document.getElementById("fidelity").addEventListener("change",e=>{state.fidelity=e.target.value;state.index=0;pause();renderAll()});
document.getElementById("play").addEventListener("click",()=>{pause();state.playing=true;state.timer=setInterval(()=>{state.index++;if(state.index>=rows().length){pause();state.index=rows().length-1}renderAll()},Math.max(25,1000*data.playback_seconds_per_simulation_second/Number(document.getElementById("speed").value||1)))});
document.getElementById("pause").addEventListener("click",pause);
document.getElementById("reset").addEventListener("click",()=>{pause();state.index=0;renderAll()});
document.getElementById("scrub").addEventListener("input",e=>{state.index=Number(e.target.value);renderAll()});
window.addEventListener("resize",renderAll);
renderAll();
</script>
</body>
</html>
"""
