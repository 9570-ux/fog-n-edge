let waterChart;
let riskChart;
const byId = id => document.getElementById(id);
const shown = value => value === null || value === undefined ? '—' : value;
const escapeHtml = value => String(value).replace(/[&<>'"]/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const badge = level => `<span class="badge ${escapeHtml(String(level).toLowerCase().replace(' ','-'))}">${escapeHtml(level)}</span>`;

async function json(url) {
  const response = await fetch(url, {cache: 'no-store'});
  if (!response.ok) throw new Error(`Request failed: ${response.status}`);
  return response.json();
}

async function loadStatus() {
  const data = await json('/api/status');
  byId('fogStatus').textContent = data.fog_data_status;
  byId('dbStatus').textContent = data.database;
  byId('identity').textContent = data.zone_id ? `${data.zone_id} / ${data.device_id}` : '—';
  byId('totalReadings').textContent = data.total_readings;
  byId('latestTimestamp').textContent = data.latest_data_timestamp || 'Waiting for sensor data...';
  byId('liveBadge').textContent = data.fog_data_status === 'DATA AVAILABLE' ? 'DATA AVAILABLE' : 'WAITING FOR DATA';
  byId('liveBadge').classList.toggle('waiting', data.fog_data_status !== 'DATA AVAILABLE');
}

async function loadLatest() {
  const {event} = await json('/api/latest');
  if (!event) return;
  byId('temperature').textContent = shown(event.temperature_c); byId('ph').textContent = shown(event.ph);
  byId('salinity').textContent = shown(event.salinity_psu); byId('turbidity').textContent = shown(event.turbidity_ntu);
  byId('oxygen').textContent = shown(event.dissolved_oxygen_mg_l);
  byId('validity').textContent = event.sensor_valid ? 'VALID' : 'INVALID';
  byId('riskScore').textContent = event.edge_risk_score === null ? 'BLOCKED' : `${event.edge_risk_score} / 100`;
  byId('riskLevel').textContent = event.edge_risk_level;
  byId('riskCard').className = `risk-card ${event.edge_risk_level.toLowerCase()}`;
}

function renderCharts(events) {
  const ordered = [...events].reverse();
  const labels = ordered.map(e => `#${e.sequence_number}`);
  byId('chartEmpty').style.display = events.length ? 'none' : 'block';
  if (typeof Chart === 'undefined' || !events.length) return;
  const waterData = {
    labels, datasets: [
      {label:'Temperature °C',data:ordered.map(e=>e.temperature_c),borderColor:'#e76f51'},
      {label:'pH',data:ordered.map(e=>e.ph),borderColor:'#7c3aed'},
      {label:'Salinity PSU',data:ordered.map(e=>e.salinity_psu),borderColor:'#0284c7'},
      {label:'Turbidity NTU',data:ordered.map(e=>e.turbidity_ntu),borderColor:'#ca8a04'},
      {label:'DO mg/L',data:ordered.map(e=>e.dissolved_oxygen_mg_l),borderColor:'#16a34a'}
    ].map(x=>({...x,tension:.25,pointRadius:2,borderWidth:2}))
  };
  const riskData = {labels,datasets:[{label:'Risk score',data:ordered.map(e=>e.edge_risk_score),borderColor:'#dc2626',backgroundColor:'#fee2e2',fill:true,tension:.25}]};
  if (waterChart) waterChart.destroy(); if (riskChart) riskChart.destroy();
  waterChart = new Chart(byId('waterChart'),{type:'line',data:waterData,options:{responsive:true,maintainAspectRatio:false}});
  riskChart = new Chart(byId('riskChart'),{type:'line',data:riskData,options:{responsive:true,maintainAspectRatio:false,scales:{y:{min:0,max:100}}}});
}

async function loadHistory() {
  const {events} = await json(`/api/history?limit=${byId('historyLimit').value}`);
  byId('historyBody').innerHTML = events.length ? events.map(e => `<tr><td>${escapeHtml(e.event_timestamp)}</td><td>${escapeHtml(e.device_id)}</td><td>${escapeHtml(e.zone_id)}</td><td>${escapeHtml(shown(e.temperature_c))}</td><td>${escapeHtml(shown(e.ph))}</td><td>${escapeHtml(shown(e.salinity_psu))}</td><td>${escapeHtml(shown(e.turbidity_ntu))}</td><td>${escapeHtml(shown(e.dissolved_oxygen_mg_l))}</td><td>${e.sensor_valid?'VALID':'INVALID'}</td><td>${escapeHtml(shown(e.edge_risk_score))}</td><td>${badge(e.edge_risk_level)}</td></tr>`).join('') : '<tr><td colspan="11">Waiting for sensor data...</td></tr>';
  renderCharts(events);
}

async function loadAlerts() {
  const level = encodeURIComponent(byId('alertLevel').value);
  const {alerts} = await json(`/api/alerts?level=${level}`);
  byId('alertsBody').innerHTML = alerts.length ? alerts.map(a => `<tr><td>${escapeHtml(a.created_timestamp)}</td><td>${escapeHtml(a.device_id)}</td><td>${escapeHtml(a.zone_id)}</td><td>${badge(a.alert_level)}</td><td>${escapeHtml(a.message)}</td><td>${escapeHtml(a.status)}</td></tr>`).join('') : '<tr><td colspan="6">No alerts recorded.</td></tr>';
}

async function loadDecision() {
  const {decision} = await json('/api/decision/latest');
  if (!decision) return;
  const displayNames = {MONITOR:'Continue monitoring',RETEST:'Retest recommended',HOLD_HARVEST:'Hold / verification recommended',COLLECT_SAMPLE:'Collect verification sample',SENSOR_MAINTENANCE:'Sensor maintenance'};
  byId('decisionAction').textContent = decision.action.replaceAll('_',' ');
  byId('decisionDisplay').textContent = displayNames[decision.action] || decision.action;
  byId('decisionPriority').textContent = decision.priority;
  byId('samplingRequired').textContent = decision.sampling_required ? 'YES' : 'NO';
  byId('currentSampleId').textContent = shown(decision.sample_id);
  byId('commandStatus').textContent = shown(decision.command_status);
  byId('decisionReason').textContent = decision.reason;
  byId('decisionCard').className = `decision-card ${decision.action.toLowerCase()}`;
}

async function loadDecisions() {
  const {decisions} = await json('/api/decisions?limit=50');
  byId('decisionsBody').innerHTML = decisions.length ? decisions.map(d => `<tr><td>${escapeHtml(d.decision_timestamp)}</td><td>${escapeHtml(d.decision_id)}</td><td>${escapeHtml(d.device_id)}</td><td>${escapeHtml(d.zone_id)}</td><td>${badge(d.risk_level)}</td><td>${escapeHtml(d.action.replaceAll('_',' '))}</td><td>${escapeHtml(d.reason)}</td><td>${escapeHtml(shown(d.sample_id))}</td><td>${escapeHtml(d.status)}</td></tr>`).join('') : '<tr><td colspan="9">Waiting for decisions...</td></tr>';
}

async function loadSamples() {
  const {samples} = await json('/api/samples?limit=100');
  byId('samplesBody').innerHTML = samples.length ? samples.map(s => `<tr><td>${escapeHtml(s.sample_id)}</td><td>${escapeHtml(s.requested_at)}</td><td>${escapeHtml(s.device_id)}</td><td>${escapeHtml(s.zone_id)}</td><td>${badge(s.risk_level)}</td><td>${escapeHtml(s.trigger_reason)}</td><td>${escapeHtml(s.command_status)}</td><td>${escapeHtml(s.collection_status)}</td><td>${escapeHtml(s.laboratory_status)}</td></tr>`).join('') : '<tr><td colspan="9">No sample requests recorded.</td></tr>';
}

async function refresh() {
  try { await Promise.all([loadStatus(),loadLatest(),loadHistory(),loadAlerts(),loadDecision(),loadDecisions(),loadSamples()]); }
  catch (error) { byId('liveBadge').textContent='DASHBOARD ERROR'; byId('liveBadge').classList.add('waiting'); console.error(error); }
}
byId('historyLimit').addEventListener('change', loadHistory);
byId('alertLevel').addEventListener('change', loadAlerts);
refresh(); setInterval(refresh, 5000);
