/*
============================================================
    Template Name: Admio - AI Bootstrap 5 Admin Dashboard Template
    Author: Themiverse
    Support: techsupport@themiverse.com
    Description: Admio - AI Bootstrap 5 Admin Dashboard Template
    Version: 1.0
============================================================ */

'use strict';

document.addEventListener('DOMContentLoaded', function () {
  if (typeof Chart === 'undefined') return;

  // Global Chart.js defaults
  Chart.defaults.font.family = "'Plus Jakarta Sans', system-ui, sans-serif";
  Chart.defaults.font.size   = 12;
  Chart.defaults.plugins.legend.labels.usePointStyle = false;
  Chart.defaults.plugins.legend.labels.boxWidth = 8;
  Chart.defaults.plugins.legend.labels.boxHeight = 8;
  Chart.defaults.plugins.legend.labels.borderRadius = 50;
  Chart.defaults.plugins.legend.labels.padding = 16;

  // Init all charts found on page
  initMainDashboardCharts();
  initAnalyticsCharts();
  initAIModelsCharts();
  initAIUsageCharts();
  initCRMCharts();
  initChartPageCharts();
});

/* ============================================================
   HELPERS
   ============================================================ */
function getTheme() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return {
    grid:   dark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.06)',
    text:   dark ? '#94A3B8' : '#6B7280',
    bg:     dark ? '#13132B' : '#FFFFFF',
    border: dark ? 'rgba(255,255,255,0.10)' : 'rgba(0,0,0,0.08)',
  };
}

const P  = '#7C3AED';
const C  = '#06B6D4';
const G  = '#10B981';
const O  = '#F59E0B';
const R  = '#EF4444';
const B  = '#3B82F6';

const ALL_CHARTS = {};

function registerChart(id, instance) {
  ALL_CHARTS[id] = instance;
}

// Update all charts on theme change
window.admioUpdateChartsTheme = function () {
  const t = getTheme();
  Object.values(ALL_CHARTS).forEach(function (chart) {
    if (!chart || !chart.options) return;
    try {
      const scales = chart.options.scales;
      if (scales) {
        Object.values(scales).forEach(function (scale) {
          if (scale.grid) scale.grid.color = t.grid;
          if (scale.ticks) scale.ticks.color = t.text;
        });
      }
      if (chart.options.plugins && chart.options.plugins.legend) {
        chart.options.plugins.legend.labels.color = t.text;
      }
      chart.update('none');
    } catch (e) {}
  });
};

function makeChart(id, type, data, options) {
  const canvas = document.getElementById(id);
  if (!canvas) return null;
  const t = getTheme();
  const baseOptions = {
    responsive: true,
    maintainAspectRatio: false,
    layout: { padding: { left: 8 } },
    plugins: {
      legend: { labels: { color: t.text } },
      tooltip: {
        backgroundColor: '#1F2937',
        titleColor: '#F9FAFB',
        bodyColor: '#D1D5DB',
        padding: 10,
        cornerRadius: 8,
        titleFont: { weight: '700' },
      }
    }
  };
  const merged = deepMerge(baseOptions, options || {});
  const chart = new Chart(canvas, { type, data, options: merged });
  registerChart(id, chart);
  return chart;
}

function deepMerge(target, source) {
  const out = Object.assign({}, target);
  for (const key in source) {
    if (source[key] && typeof source[key] === 'object' && !Array.isArray(source[key])) {
      out[key] = deepMerge(target[key] || {}, source[key]);
    } else {
      out[key] = source[key];
    }
  }
  return out;
}

/* ============================================================
   MAIN DASHBOARD CHARTS
   ============================================================ */
function initMainDashboardCharts() {
  const t = getTheme();

  // Revenue Area Chart
  makeChart('revenueChart', 'line', {
    labels: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
    datasets: [
      {
        label: 'Revenue',
        data: [42000,48000,44000,58000,62000,71000,68000,82000,88000,96000,104000,128640],
        borderColor: P,
        backgroundColor: 'rgba(124,58,237,0.10)',
        tension: 0.45,
        fill: true,
        pointRadius: 4,
        pointBackgroundColor: P,
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
      },
      {
        label: 'AI Revenue',
        data: [12000,16000,18000,24000,28000,34000,32000,42000,46000,52000,58000,72000],
        borderColor: C,
        backgroundColor: 'rgba(6,182,212,0.08)',
        tension: 0.45,
        fill: true,
        pointRadius: 4,
        pointBackgroundColor: C,
        pointBorderColor: '#fff',
        pointBorderWidth: 2,
      }
    ]
  }, {
    scales: {
      x: { grid: { color: t.grid }, ticks: { color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text, callback: v => '$' + (v/1000).toFixed(0) + 'K' } }
    }
  });

  // AI Requests Donut
  makeChart('aiRequestsChart', 'doughnut', {
    labels: ['Chat (GPT-4)', 'Code Gen', 'Analysis', 'Image Gen', 'Other'],
    datasets: [{
      data: [38, 24, 18, 12, 8],
      backgroundColor: [P, C, G, O, B],
      borderWidth: 0,
      hoverOffset: 8,
      borderRadius: 0,
    }]
  }, {
    cutout: '70%',
    plugins: { legend: { display: false } }
  });

  // Weekly Activity Bar
  makeChart('weeklyChart', 'bar', {
    labels: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
    datasets: [
      {
        label: 'AI Requests',
        data: [3200, 4100, 3800, 4600, 5200, 2400, 1800],
        backgroundColor: `rgba(124,58,237,0.8)`,
        borderRadius: 6,
      },
      {
        label: 'API Calls',
        data: [1800, 2400, 2100, 2900, 3400, 1200, 900],
        backgroundColor: `rgba(6,182,212,0.7)`,
        borderRadius: 6,
      }
    ]
  }, {
    scales: {
      x: { grid: { display: false }, ticks: { color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text } }
    }
  });
}

/* ============================================================
   ANALYTICS CHARTS
   ============================================================ */
function initAnalyticsCharts() {
  const t = getTheme();

  // Traffic Sources Line
  makeChart('trafficChart', 'line', {
    labels: ['Week 1','Week 2','Week 3','Week 4'],
    datasets: [
      { label: 'Organic', data: [4200,4800,5100,5800], borderColor: G, tension: 0.4, pointRadius: 5, pointBackgroundColor: G, pointBorderColor: '#fff', pointBorderWidth: 2 },
      { label: 'Direct',  data: [2800,3200,2900,3600], borderColor: P, tension: 0.4, pointRadius: 5, pointBackgroundColor: P, pointBorderColor: '#fff', pointBorderWidth: 2 },
      { label: 'Referral',data: [1200,1600,1800,2100], borderColor: C, tension: 0.4, pointRadius: 5, pointBackgroundColor: C, pointBorderColor: '#fff', pointBorderWidth: 2 },
    ]
  }, {
    scales: {
      x: { grid: { color: t.grid }, ticks: { color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text } }
    }
  });

  // Device Donut
  makeChart('deviceChart', 'doughnut', {
    labels: ['Desktop', 'Mobile', 'Tablet'],
    datasets: [{ data: [56, 35, 9], backgroundColor: [P, C, G], borderWidth: 0, hoverOffset: 6 }]
  }, { cutout: '68%', plugins: { legend: { position: 'bottom', labels: { color: t.text } } } });

  // Monthly Comparison Bar
  makeChart('comparisonChart', 'bar', {
    labels: ['Jan','Feb','Mar','Apr','May','Jun'],
    datasets: [
      { label: '2025', data: [38000,42000,39000,51000,58000,64000], backgroundColor: `rgba(124,58,237,0.4)`, borderRadius: 5 },
      { label: '2026', data: [48000,55000,52000,68000,75000,88000], backgroundColor: P, borderRadius: 5 },
    ]
  }, {
    scales: {
      x: { grid: { display: false }, ticks: { color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text, callback: v => '$' + (v/1000).toFixed(0) + 'K' } }
    }
  });

  // Area radar
  makeChart('radarChart', 'radar', {
    labels: ['Chat','Code','Analysis','Vision','Audio','Embedding'],
    datasets: [{
      label: 'GPT-4 Turbo',
      data: [95, 88, 92, 85, 70, 96],
      borderColor: P, backgroundColor: 'rgba(124,58,237,0.15)', pointBackgroundColor: P,
    }, {
      label: 'Claude 3',
      data: [88, 92, 96, 78, 60, 90],
      borderColor: C, backgroundColor: 'rgba(6,182,212,0.15)', pointBackgroundColor: C,
    }]
  }, {
    scales: { r: { grid: { color: t.grid }, ticks: { color: t.text, backdropColor: 'transparent' }, pointLabels: { color: t.text } } }
  });
}

/* ============================================================
   AI MODELS CHARTS
   ============================================================ */
function initAIModelsCharts() {
  const t = getTheme();

  // Model Accuracy Comparison
  makeChart('modelAccuracyChart', 'bar', {
    labels: ['GPT-4 Turbo','Claude 3 Opus','Gemini Ultra','Mistral Large','Llama 3 70B'],
    datasets: [{
      label: 'Accuracy %',
      data: [97.2, 96.8, 94.1, 91.4, 89.7],
      backgroundColor: [P, C, G, O, B],
      borderRadius: 8,
    }]
  }, {
    indexAxis: 'y',
    scales: {
      x: { min: 85, max: 100, grid: { color: t.grid }, ticks: { color: t.text, callback: v => v + '%' } },
      y: { grid: { display: false }, ticks: { color: t.text } }
    },
    plugins: { legend: { display: false } }
  });

  // Model Usage Trend
  makeChart('modelUsageChart', 'line', {
    labels: ['Jun','Jul','Aug','Sep','Oct','Nov'],
    datasets: [
      { label: 'GPT-4 Turbo', data: [8400,10200,12800,14600,16200,18940], borderColor: P, tension: 0.4, fill: false, pointRadius: 4, pointBackgroundColor: P, pointBorderColor: '#fff', pointBorderWidth: 2 },
      { label: 'Claude 3',    data: [4200,5600,7800,9400,11200,13820], borderColor: C, tension: 0.4, fill: false, pointRadius: 4, pointBackgroundColor: C, pointBorderColor: '#fff', pointBorderWidth: 2 },
      { label: 'Gemini',      data: [2100,3200,4800,6200,7800,9240], borderColor: G, tension: 0.4, fill: false, pointRadius: 4, pointBackgroundColor: G, pointBorderColor: '#fff', pointBorderWidth: 2 },
    ]
  }, {
    scales: {
      x: { grid: { color: t.grid }, ticks: { color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text, callback: v => v.toLocaleString() } }
    }
  });

  // Model Cost Donut
  makeChart('modelCostChart', 'doughnut', {
    labels: ['GPT-4 Turbo', 'Claude 3', 'Gemini Ultra', 'Other'],
    datasets: [{ data: [52, 28, 13, 7], backgroundColor: [P, C, G, O], borderWidth: 0, hoverOffset: 8 }]
  }, { cutout: '72%', plugins: { legend: { position: 'bottom', labels: { color: t.text } } } });
}

/* ============================================================
   AI USAGE CHARTS
   ============================================================ */
function initAIUsageCharts() {
  const t = getTheme();

  // Requests over time
  makeChart('usageTrendChart', 'line', {
    labels: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
    datasets: [{
      label: 'API Requests',
      data: [12000,15000,13500,18000,21000,24500,22000,28000,32000,36000,42000,48300],
      borderColor: P,
      backgroundColor: 'rgba(124,58,237,0.10)',
      tension: 0.4,
      fill: true,
      pointRadius: 4,
      pointBackgroundColor: P,
      pointBorderColor: '#fff',
      pointBorderWidth: 2,
    }]
  }, {
    scales: {
      x: { grid: { color: t.grid }, ticks: { color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text, callback: v => (v/1000).toFixed(0) + 'K' } }
    },
    plugins: { legend: { display: false } }
  });

  // Cost by feature
  makeChart('costByFeatureChart', 'bar', {
    labels: ['Chat','Code Gen','Analysis','Image Gen','Embeddings','Speech'],
    datasets: [{
      label: 'Cost ($)',
      data: [1284, 842, 612, 428, 184, 96],
      backgroundColor: [P, C, G, O, B, R],
      borderRadius: 6,
    }]
  }, {
    scales: {
      x: { grid: { display: false }, ticks: { color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text, callback: v => '$' + v } }
    },
    plugins: { legend: { display: false } }
  });

  // Token usage donut
  makeChart('tokenUsageChart', 'doughnut', {
    labels: ['Input Tokens', 'Output Tokens', 'Cached'],
    datasets: [{ data: [58, 32, 10], backgroundColor: [P, C, G], borderWidth: 0, hoverOffset: 6 }]
  }, { cutout: '72%', plugins: { legend: { position: 'bottom', labels: { color: t.text } } } });
}

/* ============================================================
   CRM CHARTS
   ============================================================ */
function initCRMCharts() {
  const t = getTheme();

  makeChart('crmForecastChart', 'line', {
    labels: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
    datasets: [
      { label: 'Actual', data: [38000,42000,39000,51000,58000,64000,71000,68000,82000,88000,96000,null], borderColor: P, backgroundColor: 'rgba(124,58,237,0.1)', tension: 0.4, fill: true, pointRadius: 4 },
      { label: 'Forecast', data: [null,null,null,null,null,null,71000,80000,87000,94000,102000,110000], borderColor: C, borderDash: [5,4], tension: 0.4, pointRadius: 0, fill: false }
    ]
  }, {
    scales: {
      x: { grid: { color: t.grid }, ticks: { color: t.text } },
      y: { grid: { color: t.grid }, ticks: { color: t.text, callback: v => '$' + (v/1000).toFixed(0) + 'K' } }
    }
  });
}

/* ============================================================
   CHART PAGE — ALL TYPES
   ============================================================ */
function initChartPageCharts() {
  const t = getTheme();

  // Line Chart
  makeChart('lineChart1', 'line', {
    labels: ['Jan','Feb','Mar','Apr','May','Jun','Jul'],
    datasets: [
      { label: 'Dataset A', data: [65,59,80,81,56,72,88], borderColor: P, tension: 0.4, fill: false, pointRadius: 5 },
      { label: 'Dataset B', data: [28,48,40,59,86,74,62], borderColor: C, tension: 0.4, fill: false, pointRadius: 5 },
    ]
  }, { scales: { x: { grid: { color: t.grid }, ticks: { color: t.text } }, y: { grid: { color: t.grid }, ticks: { color: t.text } } } });

  // Bar Chart
  makeChart('barChart1', 'bar', {
    labels: ['Q1','Q2','Q3','Q4'],
    datasets: [
      { label: '2025', data: [84000,92000,88000,110000], backgroundColor: `rgba(124,58,237,0.5)`, borderRadius: 6 },
      { label: '2026', data: [96000,108000,104000,128000], backgroundColor: P, borderRadius: 6 },
    ]
  }, { scales: { x: { grid: { display: false }, ticks: { color: t.text } }, y: { grid: { color: t.grid }, ticks: { color: t.text } } } });

  // Pie
  makeChart('pieChart1', 'pie', {
    labels: ['GPT-4','Claude','Gemini','Llama','Mistral'],
    datasets: [{ data: [38,24,18,12,8], backgroundColor: [P,C,G,O,B], borderWidth: 2, borderColor: t.bg }]
  }, { plugins: { legend: { position: 'bottom', labels: { color: t.text } } } });

  // Donut
  makeChart('donutChart1', 'doughnut', {
    labels: ['Success','Error','Timeout','Pending'],
    datasets: [{ data: [84,8,5,3], backgroundColor: [G,R,O,C], borderWidth: 0, hoverOffset: 8 }]
  }, { cutout: '70%', plugins: { legend: { position: 'bottom', labels: { color: t.text } } } });

  // Area Chart
  makeChart('areaChart1', 'line', {
    labels: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
    datasets: [{
      label: 'AI Requests',
      data: [4200,5100,4800,6200,7400,3100,2400],
      borderColor: P, backgroundColor: 'rgba(124,58,237,0.15)', tension: 0.4, fill: true, pointRadius: 4, pointBackgroundColor: P, pointBorderColor: '#fff', pointBorderWidth: 2,
    }]
  }, { scales: { x: { grid: { color: t.grid }, ticks: { color: t.text } }, y: { grid: { color: t.grid }, ticks: { color: t.text } } }, plugins: { legend: { display: false } } });

  // Radar
  makeChart('radarChart1', 'radar', {
    labels: ['Speed','Accuracy','Cost','Context','Reasoning','Code'],
    datasets: [
      { label: 'GPT-4', data: [85,97,60,95,94,92], borderColor: P, backgroundColor: 'rgba(124,58,237,0.12)', pointBackgroundColor: P },
      { label: 'Claude', data: [88,96,72,98,96,94], borderColor: C, backgroundColor: 'rgba(6,182,212,0.10)', pointBackgroundColor: C },
    ]
  }, { scales: { r: { grid: { color: t.grid }, ticks: { color: t.text, backdropColor: 'transparent' }, pointLabels: { color: t.text } } } });
}

/* ============================================================
   CHARTS Area
   ============================================================ */
   // charts area
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("ac1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  function sc(x){return{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:t.textColor}}},scales:{x:{grid:{color:t.gridColor},ticks:{color:t.textColor}},y:{grid:{color:t.gridColor},ticks:{color:t.textColor}}}};}
  new Chart(document.getElementById("ac1"),{type:"line",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{label:"Token Usage",data:[120000,150000,135000,180000,210000,245000,220000,280000,320000,360000,420000,483000],borderColor:"#7C3AED",backgroundColor:"rgba(124,58,237,0.15)",fill:true,tension:0.4,pointRadius:3,pointBackgroundColor:"#7C3AED"}]},options:sc()});
  var sc2=sc();sc2.scales.y.stacked=true;
  new Chart(document.getElementById("ac2"),{type:"line",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{label:"GPT-4",data:[8000,10000,9000,12000,14000,16000,15000,19000,21000,24000,28000,32000],borderColor:"#7C3AED",backgroundColor:"rgba(124,58,237,0.2)",fill:true,tension:0.4},{label:"Claude 3",data:[4000,5000,5500,7000,8000,10000,9500,12000,14000,16000,19000,22000],borderColor:"#06B6D4",backgroundColor:"rgba(6,182,212,0.2)",fill:true,tension:0.4},{label:"Gemini",data:[2000,2500,2800,3500,4200,5000,4800,6000,7000,8000,10000,12000],borderColor:"#10B981",backgroundColor:"rgba(16,185,129,0.2)",fill:true,tension:0.4}]},options:sc2});
  new Chart(document.getElementById("ac3"),{type:"line",data:{labels:['Week 1','Week 2','Week 3','Week 4','Week 5','Week 6','Week 7'],datasets:[{label:"API Calls",data:[4200,5100,4800,6200,7400,6800,8200],borderColor:"#F59E0B",backgroundColor:"rgba(245,158,11,0.15)",fill:true,tension:0.45,pointRadius:4,pointBackgroundColor:"#F59E0B",pointBorderColor:"#fff",pointBorderWidth:2}]},options:sc()});
  new Chart(document.getElementById("ac4"),{type:"line",data:{labels:["Q1","Q2","Q3","Q4"],datasets:[{label:"2025",data:[84000,92000,88000,110000],borderColor:"rgba(124,58,237,0.4)",backgroundColor:"rgba(124,58,237,0.06)",fill:true,tension:0.4},{label:"2026",data:[96000,108000,104000,128000],borderColor:"#7C3AED",backgroundColor:"rgba(124,58,237,0.12)",fill:true,tension:0.4}]},options:sc()});
});

// charts bar
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("bc1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  function sc(h){return{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:t.textColor}}},scales:{x:{grid:{display:!h,color:t.gridColor},ticks:{color:t.textColor}},y:{grid:{color:t.gridColor,display:h},ticks:{color:t.textColor}}}};}
  new Chart(document.getElementById("bc1"),{type:"bar",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{label:"Revenue",data:[42000,48000,44000,58000,62000,71000,68000,82000,88000,96000,104000,128640],backgroundColor:"#7C3AED",borderRadius:6}]},options:sc(false)});
  new Chart(document.getElementById("bc2"),{type:"bar",data:{labels:["Q1","Q2","Q3","Q4"],datasets:[{label:"2025",data:[84000,92000,88000,110000],backgroundColor:"rgba(124,58,237,0.5)",borderRadius:5},{label:"2026",data:[96000,108000,104000,128640],backgroundColor:"#7C3AED",borderRadius:5}]},options:sc(false)});
  new Chart(document.getElementById("bc3"),{type:"bar",data:{labels:["GPT-4 Turbo","Claude 3 Opus","Gemini Ultra","Mistral Large","Llama 3 70B"],datasets:[{label:"Accuracy %",data:[97.2,96.8,94.1,91.4,89.7],backgroundColor:["#7C3AED","#06B6D4","#10B981","#F59E0B","#3B82F6"],borderRadius:6}]},options:{...sc(true),indexAxis:"y",scales:{x:{min:85,max:100,grid:{color:t.gridColor},ticks:{color:t.textColor,callback:function(v){return v+"%"}}},y:{grid:{display:false},ticks:{color:t.textColor}}}}});
  var sc4=sc(false);sc4.scales.x.stacked=true;sc4.scales.y.stacked=true;
  new Chart(document.getElementById("bc4"),{type:"bar",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{label:"GPT-4",data:[3000,3800,3500,4800,5200,6100,5800,7200,8000,9000,10500,12200],backgroundColor:"#7C3AED",borderRadius:4},{label:"Claude 3",data:[1500,2000,2200,2800,3200,3800,3600,4600,5200,5800,7000,8400],backgroundColor:"#06B6D4",borderRadius:4},{label:"Other",data:[800,1200,1000,1500,1800,2100,2000,2400,2800,3200,3800,4400],backgroundColor:"#10B981",borderRadius:4}]},options:sc4});
});

// Charts Funnel
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("fn1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  // Funnel via horizontal bar
  new Chart(document.getElementById("fn1"),{type:"bar",data:{labels:["New Leads","Contacted","Qualified","Proposal Sent","Negotiation","Closed Won"],datasets:[{label:"Count",data:[284,210,148,92,54,38],backgroundColor:["#7C3AED","rgba(124,58,237,0.85)","rgba(124,58,237,0.7)","rgba(124,58,237,0.55)","rgba(124,58,237,0.4)","rgba(16,185,129,0.9)"],borderRadius:6}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:"y",plugins:{legend:{display:false}},scales:{x:{grid:{color:t.gridColor},ticks:{color:t.textColor}},y:{grid:{display:false},ticks:{color:t.textColor}}}}});
  new Chart(document.getElementById("fn2"),{type:"bar",data:{labels:["Lead","MQL","SQL","Opportunity","Proposal","Won"],datasets:[{label:"Value ($K)",data:[482,380,295,214,148,96],backgroundColor:"#06B6D4",borderRadius:6,barPercentage:0.6}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:"y",plugins:{legend:{display:false}},scales:{x:{grid:{color:t.gridColor},ticks:{color:t.textColor,callback:function(v){return"$"+v+"K"}}},y:{grid:{display:false},ticks:{color:t.textColor}}}}});
  // Timeline via grouped bar
  new Chart(document.getElementById("fn3"),{type:"bar",data:{labels:["Phase 1","Phase 2","Phase 3","Phase 4","Phase 5"],datasets:[{label:"Start",data:[0,2,4,6,9],backgroundColor:"transparent",borderWidth:0},{label:"Duration",data:[2,2,2,3,3],backgroundColor:["#7C3AED","#06B6D4","#10B981","#F59E0B","#3B82F6"],borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,indexAxis:"y",plugins:{legend:{display:false}},scales:{x:{min:0,max:12,stacked:true,grid:{color:t.gridColor},ticks:{color:t.textColor,callback:function(v){return"Month "+v}}},y:{stacked:true,grid:{display:false},ticks:{color:t.textColor}}}}});
  // Waterfall via grouped bar
  new Chart(document.getElementById("fn4"),{type:"bar",data:{labels:["Start","Q1","Q2","Q3","Q4","End"],datasets:[{label:"Base",data:[0,42000,0,0,0,0],backgroundColor:"transparent",borderWidth:0},{label:"Change",data:[42000,52000,60000,88000,128640,128640],backgroundColor:["rgba(124,58,237,0.8)","rgba(16,185,129,0.8)","rgba(6,182,212,0.8)","rgba(16,185,129,0.8)","rgba(16,185,129,0.8)","rgba(124,58,237,0.9)"],borderRadius:5}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{grid:{display:false},ticks:{color:t.textColor}},y:{grid:{color:t.gridColor},ticks:{color:t.textColor,callback:function(v){return"$"+(v/1000).toFixed(0)+"K"}}}}}});
});

// Charts Heatmap
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("hm1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  // Simulate heatmap with stacked bar
  var hours=["12AM","3AM","6AM","9AM","12PM","3PM","6PM","9PM"];
  var days=["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
  function rndData(){return hours.map(function(){return Math.floor(Math.random()*100);});}
  var colors=["rgba(237,233,254,0.5)","rgba(196,181,253,0.7)","rgba(167,139,250,0.8)","rgba(139,92,246,0.85)","rgba(109,40,217,0.9)","rgba(91,21,180,1)"];
  function mapColor(v){return v<17?colors[0]:v<33?colors[1]:v<50?colors[2]:v<67?colors[3]:v<84?colors[4]:colors[5];}
  // Use bar chart to simulate heatmap
  var datasets=days.map(function(d,i){return{label:d,data:hours.map(function(){return 1;}),backgroundColor:rndData().map(mapColor),borderRadius:3,borderWidth:2,borderColor:"#fff",categoryPercentage:0.95,barPercentage:0.95};});
  var opts={responsive:true,maintainAspectRatio:false,plugins:{legend:{display:false}},scales:{x:{stacked:true,grid:{display:false},ticks:{color:t.textColor}},y:{stacked:true,grid:{display:false},ticks:{color:t.textColor}}}};
  new Chart(document.getElementById("hm1"),{type:"bar",data:{labels:hours,datasets:datasets},options:opts});
  new Chart(document.getElementById("hm2"),{type:"bar",data:{labels:hours,datasets:datasets.slice(0,5)},options:opts});
  new Chart(document.getElementById("hm3"),{type:"bar",data:{labels:["0-4","4-8","8-12","12-16","16-20","20-24"],datasets:[{label:"Mon-Fri",data:[5,15,60,80,55,25],backgroundColor:"rgba(124,58,237,0.8)",borderRadius:4},{label:"Sat-Sun",data:[3,10,30,45,40,20],backgroundColor:"rgba(6,182,212,0.8)",borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:t.textColor}}},scales:{x:{grid:{display:false},ticks:{color:t.textColor}},y:{grid:{color:t.gridColor},ticks:{color:t.textColor}}}}});
  new Chart(document.getElementById("hm4"),{type:"bar",data:{labels:["Chat","Code","Analysis","Vision","Audio","Embed"],datasets:[{label:"GPT-4",data:[97,92,95,88,72,96],backgroundColor:"rgba(124,58,237,0.8)",borderRadius:4},{label:"Claude 3",data:[96,94,96,78,60,90],backgroundColor:"rgba(6,182,212,0.8)",borderRadius:4},{label:"Gemini",data:[90,86,92,94,68,84],backgroundColor:"rgba(16,185,129,0.8)",borderRadius:4}]},options:{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:t.textColor}}},scales:{x:{grid:{display:false},ticks:{color:t.textColor}},y:{grid:{color:t.gridColor},ticks:{color:t.textColor,callback:function(v){return v+"%"}}}}}});
});

// Charts line
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("lc1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  function sc(x){return{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:t.textColor}}},scales:{x:{grid:{color:t.gridColor},ticks:{color:t.textColor}},y:{grid:{color:t.gridColor},ticks:{color:t.textColor}}}};}
  new Chart(document.getElementById("lc1"),{type:"line",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{label:"AI Requests",data:[12000,15000,13500,18000,21000,24500,22000,28000,32000,36000,42000,48300],borderColor:"#7C3AED",backgroundColor:"rgba(124,58,237,0.1)",fill:true,tension:0,pointRadius:4,pointBackgroundColor:"#7C3AED",pointBorderColor:"#fff",pointBorderWidth:2}]},options:sc()});
  new Chart(document.getElementById("lc2"),{type:"line",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{label:"Revenue",data:[42000,48000,44000,58000,62000,71000,68000,82000,88000,96000,104000,128640],borderColor:"#7C3AED",fill:false,tension:0.4,pointRadius:3},{label:"AI Revenue",data:[12000,16000,18000,24000,28000,34000,32000,42000,46000,52000,58000,72000],borderColor:"#06B6D4",fill:false,tension:0.4,pointRadius:3},{label:"Costs",data:[8000,9000,8500,11000,12000,14000,13500,16000,17500,19000,21000,25600],borderColor:"#EF4444",fill:false,tension:0.4,pointRadius:3}]},options:sc()});
  new Chart(document.getElementById("lc3"),{type:"line",data:{labels:['Week 1','Week 2','Week 3','Week 4','Week 5','Week 6','Week 7'],datasets:[{label:"Users",data:[3200,4100,3800,5200,4600,6100,7400],borderColor:"#10B981",backgroundColor:"rgba(16,185,129,0.12)",fill:true,tension:0.5,pointRadius:5,pointBackgroundColor:"#10B981",pointBorderColor:"#fff",pointBorderWidth:2}]},options:sc()});
  new Chart(document.getElementById("lc4"),{type:"line",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{label:"Deployments",data:[3,4,3,5,4,6,5,7,6,8,7,10],borderColor:"#F59E0B",stepped:true,fill:false,pointRadius:4}]},options:sc()});
});

// Charts Mixed
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("mc1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  function sc(y1){return{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:t.textColor}}},scales:{x:{grid:{display:false},ticks:{color:t.textColor}},y:{grid:{color:t.gridColor},ticks:{color:t.textColor}},y1:y1?{position:"right",grid:{display:false},ticks:{color:t.textColor}}:undefined}};}
  new Chart(document.getElementById("mc1"),{type:"bar",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{type:"bar",label:"Revenue",data:[42,48,44,58,62,71,68,82,88,96,104,128],backgroundColor:"#7C3AED",borderRadius:5,yAxisID:"y"},{type:"line",label:"Orders",data:[1800,2100,1950,2400,2600,2900,2700,3200,3400,3800,4200,4800],borderColor:"#06B6D4",backgroundColor:"rgba(6,182,212,0.1)",fill:false,tension:0.4,pointRadius:4,yAxisID:"y1"}]},options:sc(true)});
  new Chart(document.getElementById("mc2"),{type:"line",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{label:"AI Cost",data:[1200,1500,1350,1800,2100,2400,2200,2700,3100,3500,4000,4800],borderColor:"#F59E0B",backgroundColor:"rgba(245,158,11,0.1)",fill:true,tension:0.4},{label:"Budget",data:[3000,3000,3000,3500,3500,3500,4000,4000,4000,5000,5000,5000],borderColor:"#EF4444",borderDash:[6,4],fill:false,pointRadius:0}]},options:sc(false)});
  new Chart(document.getElementById("mc3"),{type:"bar",data:{labels:["Q1","Q2","Q3","Q4"],datasets:[{type:"bar",label:"GPT-4 Cost",data:[1200,1800,1600,2100],backgroundColor:"#7C3AED",borderRadius:4,stack:"costs"},{type:"bar",label:"Claude Cost",data:[600,900,800,1100],backgroundColor:"#06B6D4",borderRadius:4,stack:"costs"},{type:"line",label:"Total Budget",data:[2500,3200,3000,4000],borderColor:"#F59E0B",borderDash:[5,3],fill:false,pointRadius:5}]},options:sc(false)});
  new Chart(document.getElementById("mc4"),{type:"bar",data:{labels:['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],datasets:[{type:"bar",label:"Requests (K)",data:[12,15,13.5,18,21,24.5,22,28,32,36,42,48.3],backgroundColor:"rgba(124,58,237,0.6)",borderRadius:5},{type:"line",label:"Accuracy %",data:[92,93,92.5,94,94.5,95,94.8,96,96.5,97,97.1,97.2],borderColor:"#10B981",fill:false,tension:0.4,pointRadius:3,yAxisID:"y1"}]},options:sc(true)});
});

// Charts pie
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("pc1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  var po={responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{color:t.textColor,padding:14}}}};
  new Chart(document.getElementById("pc1"),{type:"pie",data:{labels:["GPT-4","Claude 3","Gemini","Mistral","Llama"],datasets:[{data:[38,24,18,12,8],backgroundColor:["#7C3AED","#06B6D4","#10B981","#F59E0B","#3B82F6"],borderWidth:2,borderColor:"#fff",hoverOffset:8}]},options:po});
  new Chart(document.getElementById("pc2"),{type:"doughnut",data:{labels:["Chat","Code Gen","Analysis","Image Gen","Embeddings"],datasets:[{data:[38,24,18,12,8],backgroundColor:["#7C3AED","#06B6D4","#10B981","#F59E0B","#3B82F6"],borderWidth:0,hoverOffset:8}]},options:{...po,cutout:"72%"}});
  new Chart(document.getElementById("pc3"),{type:"doughnut",data:{labels:["Used","Remaining"],datasets:[{data:[57,43],backgroundColor:["#7C3AED","rgba(124,58,237,0.1)"],borderWidth:0}]},options:{...po,cutout:"78%",plugins:{legend:{display:false}}}});
  new Chart(document.getElementById("pc4"),{type:"doughnut",data:{labels:["Input Tokens","Output Tokens","Cached"],datasets:[{data:[58,32,10],backgroundColor:["#7C3AED","#06B6D4","#10B981"],borderWidth:0,hoverOffset:6}]},options:{...po,cutout:"70%",circumference:180,rotation:-90}});
});

// Charts Radar
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("rc1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  var ro={responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:t.textColor}}},scales:{r:{grid:{color:t.gridColor},ticks:{color:t.textColor,backdropColor:"transparent"},pointLabels:{color:t.textColor}}}};
  new Chart(document.getElementById("rc1"),{type:"radar",data:{labels:["Speed","Accuracy","Cost","Context","Reasoning","Code"],datasets:[{label:"GPT-4 Turbo",data:[85,97,60,95,94,92],borderColor:"#7C3AED",backgroundColor:"rgba(124,58,237,0.12)",pointBackgroundColor:"#7C3AED"}]},options:ro});
  new Chart(document.getElementById("rc2"),{type:"radar",data:{labels:["Speed","Accuracy","Cost","Context","Reasoning","Code"],datasets:[{label:"GPT-4",data:[85,97,60,95,94,92],borderColor:"#7C3AED",backgroundColor:"rgba(124,58,237,0.1)",pointBackgroundColor:"#7C3AED"},{label:"Claude 3",data:[88,96,72,98,96,94],borderColor:"#06B6D4",backgroundColor:"rgba(6,182,212,0.1)",pointBackgroundColor:"#06B6D4"},{label:"Gemini",data:[80,94,65,90,88,86],borderColor:"#10B981",backgroundColor:"rgba(16,185,129,0.1)",pointBackgroundColor:"#10B981"}]},options:ro});
  var po={responsive:true,maintainAspectRatio:false,plugins:{legend:{position:"bottom",labels:{color:t.textColor}}}};
  new Chart(document.getElementById("rc3"),{type:"polarArea",data:{labels:["Chat","Code","Analysis","Vision","Audio","Embed"],datasets:[{data:[38,24,18,10,6,4],backgroundColor:["rgba(124,58,237,0.7)","rgba(6,182,212,0.7)","rgba(16,185,129,0.7)","rgba(245,158,11,0.7)","rgba(239,68,68,0.7)","rgba(59,130,246,0.7)"],borderWidth:0}]},options:po});
  new Chart(document.getElementById("rc4"),{type:"polarArea",data:{labels:["Accuracy","Speed","Cost Eff.","Context","Support"],datasets:[{data:[97,85,72,88,90],backgroundColor:["rgba(124,58,237,0.6)","rgba(6,182,212,0.6)","rgba(16,185,129,0.6)","rgba(245,158,11,0.6)","rgba(59,130,246,0.6)"],borderWidth:0}]},options:po});
});

// Charts scatter
document.addEventListener("DOMContentLoaded",function(){
  if (!document.getElementById("sc1")) return;
  var t=window.admioGetChartDefaults?window.admioGetChartDefaults():{gridColor:"rgba(0,0,0,.06)",textColor:"#9CA3AF"};
  function sc(){return{responsive:true,maintainAspectRatio:false,plugins:{legend:{labels:{color:t.textColor}}},scales:{x:{grid:{color:t.gridColor},ticks:{color:t.textColor}},y:{grid:{color:t.gridColor},ticks:{color:t.textColor}}}};}
  function rnd(n,mn,mx){var a=[];for(var i=0;i<n;i++)a.push({x:+(Math.random()*(mx-mn)+mn).toFixed(1),y:+(Math.random()*(mx-mn)+mn).toFixed(1)});return a;}
  new Chart(document.getElementById("sc1"),{type:"scatter",data:{datasets:[{label:"Model A",data:rnd(30,1,10),backgroundColor:"rgba(124,58,237,0.6)",pointRadius:6},{label:"Model B",data:rnd(30,2,12),backgroundColor:"rgba(6,182,212,0.6)",pointRadius:6}]},options:sc()});
  function rndBub(n){var a=[];for(var i=0;i<n;i++)a.push({x:+(Math.random()*100).toFixed(1),y:+(Math.random()*100).toFixed(1),r:+(Math.random()*20+5).toFixed(1)});return a;}
  new Chart(document.getElementById("sc2"),{type:"bubble",data:{datasets:[{label:"GPT-4",data:rndBub(15),backgroundColor:"rgba(124,58,237,0.5)"},{label:"Claude 3",data:rndBub(15),backgroundColor:"rgba(6,182,212,0.5)"},{label:"Gemini",data:rndBub(10),backgroundColor:"rgba(16,185,129,0.5)"}]},options:sc()});
  new Chart(document.getElementById("sc3"),{type:"scatter",data:{datasets:[{label:"Cost vs Accuracy",data:[{x:45,y:97.2},{x:35,y:96.8},{x:40,y:94.1},{x:28,y:91.4},{x:0,y:89.7}],backgroundColor:["#7C3AED","#06B6D4","#10B981","#F59E0B","#3B82F6"],pointRadius:12,pointStyle:"circle"}]},options:{...sc(),plugins:{legend:{display:false},tooltip:{callbacks:{label:function(ctx){return ctx.raw.x===0?"Llama Free":"$"+ctx.raw.x+"/1K — "+ctx.raw.y+"%"}}}}}});
  new Chart(document.getElementById("sc4"),{type:"scatter",data:{datasets:[{label:"Latency vs Quality",data:rnd(40,0.5,3.5).map(function(p){return{x:p.x,y:+(90+p.x*2+Math.random()*2-1).toFixed(1)}})  ,backgroundColor:"rgba(245,158,11,0.7)",pointRadius:7}]},options:{...sc(),scales:{x:{...sc().scales.x,title:{display:true,text:"Latency (s)",color:t.textColor}},y:{...sc().scales.y,title:{display:true,text:"Quality (%)",color:t.textColor}}}}});
});