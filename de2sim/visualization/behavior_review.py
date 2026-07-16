"""Standalone human-review page for Phase 4A behavior proposals."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class BehaviorReviewError(Exception):
    """Controlled behavior-review rendering failure."""


def build_behavior_review_data(asot: dict[str, Any], proposals_payload: dict[str, Any]) -> dict[str, Any]:
    proposals = [item for item in proposals_payload.get("proposals", []) if isinstance(item, dict)]
    components = {str(item.get("stable_id", "")): item for item in _items(asot.get("components"))}
    requirements = {str(item.get("stable_id", "")): item for item in _items(asot.get("requirements"))}
    parameters = {str(item.get("stable_id", "")): item for item in _items(asot.get("parameters"))}
    behaviors = {str(item.get("stable_id", "")): item for item in _items(asot.get("behaviors"))}
    provenance = {str(item.get("provenance_id", "")): item for item in _items(asot.get("provenance"))}
    cards = []
    for proposal in proposals:
        cards.append(
            {
                "proposal": proposal,
                "component": _brief(components.get(str(proposal.get("owning_component_id", "")), {}), "stable_id"),
                "requirements": [_brief(requirements.get(ref, {}), "stable_id") for ref in proposal.get("referenced_requirement_ids", [])],
                "parameters": [_brief(parameters.get(ref, {}), "stable_id") for ref in proposal.get("referenced_parameter_ids", [])],
                "behaviors": [_brief(behaviors.get(ref, {}), "stable_id") for ref in proposal.get("referenced_behavior_ids", [])],
                "provenance": [_brief(provenance.get(ref, {}), "provenance_id") for ref in proposal.get("source_provenance_ids", [])],
            }
        )
    return {
        "schema_version": "de2sim.behavior_review.v1",
        "asot_id": str(asot.get("asot_id", "")),
        "provider": str(proposals_payload.get("provider", "")),
        "model": str(proposals_payload.get("model", "")),
        "prompt_hash": str(proposals_payload.get("prompt_hash", "")),
        "external_call_metadata": proposals_payload.get("external_call_metadata", {}) if isinstance(proposals_payload.get("external_call_metadata"), dict) else {},
        "cards": cards,
    }


def write_behavior_review(asot: dict[str, Any], proposals_payload: dict[str, Any], path: Path | str) -> Path:
    target = Path(path)
    data = build_behavior_review_data(asot, proposals_payload)
    target.write_text(render_behavior_review_html(data), encoding="utf-8", newline="\n")
    return target


def render_behavior_review_html(data: dict[str, Any]) -> str:
    data_text = _json_for_script_data(data)
    return _HTML.replace("__BEHAVIOR_REVIEW_DATA__", data_text)


def _json_for_script_data(data: dict[str, Any]) -> str:
    text = json.dumps(data, indent=2, sort_keys=False, ensure_ascii=False)
    return (
        text.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def _brief(item: dict[str, Any], id_key: str) -> dict[str, Any]:
    return {
        "id": str(item.get(id_key, "")),
        "name": str(item.get("name") or item.get("requirement_id") or item.get("source_relative_path") or ""),
        "text": str(item.get("text") or item.get("description") or item.get("evidence_text") or ""),
    }


def _items(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DE2Sim Behavior Review</title>
<style>
:root{color-scheme:light;--bg:#f6f7f9;--panel:#fff;--ink:#17202a;--muted:#5b6673;--line:#cfd6df;--accent:#145ea8;--good:#1c7c54;--bad:#a33838;--warn:#9a6400}
*{box-sizing:border-box}body{margin:0;font:14px/1.45 system-ui,Segoe UI,Arial,sans-serif;background:var(--bg);color:var(--ink)}header{padding:18px 22px;background:#17202a;color:#fff}h1{font-size:20px;margin:0 0 6px}main{padding:18px 22px;display:grid;gap:14px}.meta{display:flex;gap:10px;flex-wrap:wrap;color:#dbe5ef}.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:14px;display:grid;gap:12px}.card h2{font-size:18px;margin:0}.grid{display:grid;grid-template-columns:minmax(360px,1.1fr) minmax(320px,.9fr);gap:14px}.section{border-top:1px solid var(--line);padding-top:10px}.label{font-weight:700;color:#334155;margin-bottom:4px}.pill{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 8px;margin:2px;color:#334155}.warn{color:var(--warn)}.machine{width:100%;height:150px;background:#fbfcfe;border:1px solid var(--line);border-radius:6px}.machine circle{fill:#eaf3ff;stroke:#145ea8;stroke-width:2}.machine line{stroke:#546576;stroke-width:1.7}.machine path{fill:#546576}.machine text{font-size:11px;fill:#17202a}.actions{display:flex;gap:8px;flex-wrap:wrap}.actions button,#download{border:1px solid var(--line);border-radius:6px;background:#fff;padding:7px 10px;cursor:pointer}.actions button[data-status=approved]{border-color:var(--good)}.actions button[data-status=rejected]{border-color:var(--bad)}.actions button[data-status=needs_revision]{border-color:var(--warn)}.decision{font-weight:700}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f8;padding:8px;border-radius:6px}.list{display:grid;gap:6px}@media(max-width:850px){.grid{grid-template-columns:1fr}}
.badge{display:inline-block;background:#fff8e6;border:1px solid #e4b949;border-radius:999px;color:#684400;font-weight:700;margin:2px 0 0;padding:3px 9px}
</style>
</head>
<body>
<header><h1>Behavior Proposal Review</h1><div class="meta" id="meta"></div></header>
<main><button id="download" type="button">Download decisions JSON</button><svg class="machine" role="img" aria-label="State-machine diagram prototype" hidden></svg><div id="cards"></div></main>
<script id="behavior-review-data" type="application/json">__BEHAVIOR_REVIEW_DATA__</script>
<script>
"use strict";
const data = JSON.parse(document.getElementById("behavior-review-data").textContent);
const decisions = new Map();
function txt(el,value){el.textContent = value == null ? "" : String(value);}
function child(tag,parent,attrs){const el=document.createElement(tag);for(const k in attrs||{})el.setAttribute(k,attrs[k]);parent.appendChild(el);return el;}
function svgChild(tag,parent,attrs){const el=document.createElementNS("http://www.w3.org/2000/svg",tag);for(const k in attrs||{})el.setAttribute(k,attrs[k]);parent.appendChild(el);return el;}
function clear(el){while(el.firstChild)el.removeChild(el.firstChild);}
function list(parent,title,items,key){const s=child("div",parent,{class:"section"});const l=child("div",s,{class:"label"});txt(l,title);const wrap=child("div",s,{class:"list"});if(!items||!items.length){txt(wrap,"None");return}items.forEach(item=>{const p=child("div",wrap,{});txt(p,(item.id||"")+" "+(item.name||"")+" "+(item[key]||""));});}
function kv(parent,title,value){const s=child("div",parent,{class:"section"});const l=child("div",s,{class:"label"});txt(l,title);const p=child("div",s,{});txt(p,Array.isArray(value)?(value.join(", ")||"None"):value||"None");}
function setDecision(id,status){if(status)decisions.set(id,{proposal_id:id,approval_status:status});else decisions.delete(id);render();}
function orderedStates(proposal){const states=[];const seen=new Set();(proposal.transitions||[]).forEach(t=>{[t.from,t.to].forEach(s=>{s=String(s||"");if(s&&!seen.has(s)){states.push(s);seen.add(s);}});});(proposal.states||[]).forEach(s=>{s=String(s||"");if(s&&!seen.has(s)){states.push(s);seen.add(s);}});return states;}
function clippedLabel(value){const text=String(value||"");return text.length>30?text.slice(0,27)+"...":text;}
function enrichmentText(p){const e=p.local_ai_enrichment||{};const out=[];function add(path,value){if(value&&String(value).trim())out.push(path+": "+String(value).trim());else out.push(path+": Not supplied by the local model")}add("$.behavior_summary",e.behavior_summary);["preflight","mission_flight","return_to_base","landed"].forEach(s=>add("$.state_descriptions."+s,(e.state_descriptions||{})[s]));["preflight_to_mission_flight","mission_flight_to_return_to_base","return_to_base_to_landed"].forEach(k=>add("$.transition_rationale."+k,(e.transition_rationale||{})[k]));["preflight","mission_flight","return_to_base","landed"].forEach(s=>{const a=(e.state_actions||{})[s]||[];add("$.state_actions."+s,a.join("; "))});["risks","assumptions","limitations"].forEach(k=>{const a=e[k]||[];add("$."+k,a.join("; "))});return out.join("\\n")}
function yesNo(value){return value?"yes":"no"}
function drawMachine(parent,proposal){const states=orderedStates(proposal);const transitions=proposal.transitions||[];const gap=155;const width=Math.max(440,120+gap*Math.max(1,states.length-1));const y=86;const svg=svgChild("svg",parent,{class:"machine",role:"img","aria-label":"State-machine diagram",viewBox:"0 0 "+width+" 150"});const defs=svgChild("defs",svg,{});const marker=svgChild("marker",defs,{id:"arrow-"+proposal.proposal_id,viewBox:"0 0 10 10",refX:"9",refY:"5",markerWidth:"6",markerHeight:"6",orient:"auto-start-reverse"});svgChild("path",marker,{d:"M0 0 L10 5 L0 10 Z"});const byState=new Map();states.forEach((state,index)=>byState.set(String(state),60+index*gap));transitions.forEach(t=>{const start=byState.get(String(t.from||"")),end=byState.get(String(t.to||""));if(start==null||end==null)return;svgChild("line",svg,{x1:start+31,y1:y,x2:end-31,y2:y,"marker-end":"url(#arrow-"+proposal.proposal_id+")"});const label=svgChild("text",svg,{x:(start+end)/2,y:24,"text-anchor":"middle"});txt(label,clippedLabel(t.trigger||t.guard||t.action||""));});states.forEach((state,index)=>{const x=60+index*gap;svgChild("circle",svg,{cx:x,cy:y,r:28});const label=svgChild("text",svg,{x:x,y:y+4,"text-anchor":"middle"});txt(label,clippedLabel(state));});}
function renderMeta(){const m=document.getElementById("meta");clear(m);["ASOT "+data.asot_id,"provider "+data.provider,"model "+data.model,"prompt "+data.prompt_hash].forEach(v=>{const s=child("span",m,{});txt(s,v);});}
function render(){renderMeta();const root=document.getElementById("cards");clear(root);data.cards.forEach(card=>{const p=card.proposal;const c=child("article",root,{class:"card"});const h=child("h2",c,{});txt(h,p.name+" ("+p.proposal_id+")");if(p.generated_by==="offline_template"){const badge=child("div",c,{class:"badge"});txt(badge,"Deterministic offline template — not generative AI");}if(p.generated_by==="external_generative_ai"){const badge=child("div",c,{class:"badge"});txt(badge,"External generative-AI output");}if(p.generated_by==="local_generative_ai"){const badge=child("div",c,{class:"badge"});txt(badge,"Confirmed Local Generative AI");}const grid=child("div",c,{class:"grid"});const left=child("div",grid,{});const right=child("div",grid,{});kv(left,"Description",p.description);kv(left,"States",orderedStates(p));kv(left,"Transitions",p.transitions.map(t=>(t.from||"")+" -> "+(t.to||"")+" / "+(t.trigger||"")));kv(left,"Triggers",p.triggers);kv(left,"Guards",p.guards);kv(left,"Actions",p.actions);const holder=child("div",right,{class:"section"});const label=child("div",holder,{class:"label"});txt(label,"State machine");drawMachine(holder,p);kv(right,"Provider and model",p.provider+" / "+p.model);if(p.generated_by==="local_generative_ai"){kv(right,"ASOT-derived deterministic structure","name: "+p.name+"\\nstates: "+orderedStates(p).join(" -> ")+"\\ntransitions: "+p.transitions.map(t=>(t.from||"")+" -> "+(t.to||"")).join(", ")+"\\nguard: battery_state <= battery_threshold\\nauthoritative references: "+[].concat(p.referenced_requirement_ids||[],p.referenced_parameter_ids||[],p.referenced_behavior_ids||[],p.source_provenance_ids||[]).join(", "));kv(right,"Local generative-AI enrichment","descriptions, actions, rationale, risks, assumptions, and limitations only\\nThe model did not generate authoritative IDs or engineering facts.");}const repairUsed=((data.external_call_metadata||{}).repair_attempted||p.repair_attempted)?"used":"not used";kv(right,"AI evidence","Generation mode: "+(p.generation_mode==="canonical_asot_scaffold_plus_local_ai_enrichment"?"ASOT scaffold plus AI enrichment":p.generation_mode||"")+"\\nprovider: "+(p.provider==="ollama"?"Ollama":p.provider)+"\\nmodel: "+p.model+"\\nlocal inference confirmed: "+(p.actual_local_model_inference_occurred?"true":"false")+"\\nactual external API call: "+(p.actual_external_api_call_occurred?"true":"false")+"\\nLocal JSON syntax repair: "+repairUsed+"\\nprompt hash: "+p.prompt_hash+"\\nresponse hash: "+(p.response_hash||"not available")+"\\nenrichment hash: "+(p.enrichment_hash||"not available")+"\\nvalidation status: "+((p.validation_warnings||[]).length?"warnings":"passed"));kv(right,"Confidence",p.confidence);kv(right,"Assumptions",p.assumptions);kv(right,"Risks",p.risks);kv(right,"Validation warnings",p.validation_warnings);list(right,"Linked requirements",card.requirements,"text");list(right,"Linked parameters",card.parameters,"text");list(right,"Linked source-derived behaviors",card.behaviors,"text");list(right,"Linked ASOT evidence",card.provenance,"text");const a=child("div",c,{class:"actions"});[["approved","Approve"],["rejected","Reject"],["needs_revision","Needs revision"],["","Reset decision"]].forEach(([status,labelText])=>{const b=child("button",a,{type:"button","data-status":status});txt(b,labelText);b.addEventListener("click",()=>setDecision(p.proposal_id,status));});const d=child("div",c,{class:"decision"});txt(d,"Decision: "+((decisions.get(p.proposal_id)||{}).approval_status||"not selected"));});}
document.getElementById("download").addEventListener("click",()=>{const payload={schema_version:"de2sim.behavior_decisions.v1",decisions:[...decisions.values()]};const blob=new Blob([JSON.stringify(payload,null,2)+"\\n"],{type:"application/json"});const url=URL.createObjectURL(blob);const a=document.createElement("a");a.href=url;a.download="behavior_decisions.json";a.click();URL.revokeObjectURL(url);});
render();
</script>
</body>
</html>
"""
