let researchJob = '';
let researchOffset = 0;
let researchReportKey = '';
let researchBusy = false;
let researchDecisionOffset = 0;
let researchDecisionTotal = 0;

async function researchRequest(path, body) {
  const response = await fetch('/api/research' + path, body === undefined ? {} : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)
  });
  const data = await response.json();
  if (!response.ok) throw Error(typeof data.detail === 'string' ? data.detail : 'Research request failed');
  return data;
}

function researchSettings() {
  return {run_minutes: Number(element('research-minutes').value), max_batches: Number(element('research-batches').value)};
}

function researchFinding(finding, job) {
  const card = makeNode('section', '', 'source');
  card.append(makeNode('h4', finding.title + ' / ' + finding.heading),
    makeNode('p', finding.author + ' · ' + finding.kind, 'muted'), makeNode('blockquote', finding.quote));
  const link = makeNode('a', 'Read the full original section');
  link.href = '/api/research/' + encodeURIComponent(job) + '/source/' + finding.id;
  link.target = '_blank';
  link.rel = 'noopener';
  card.append(link);
  return card;
}

function renderResearchReport(job) {
  const key = job.id + ':' + job.report_root + ':' + job.report_snapshot;
  if (researchReportKey === key) return;
  researchReportKey = key;
  const container = element('research-report');
  container.replaceChildren();
  if (!job.report) return;
  const report = job.report;
  const optimized = job.research_mode === 'optimized';
  container.append(makeNode('h3', 'Research report'), makeNode('p',
    `Report snapshot: ${job.report_sections.toLocaleString()} of ${job.total_sections.toLocaleString()} ${optimized ? "selected" : "scoped"} sections examined. ${optimized ? `The full scope contains ${job.eligible_sections.toLocaleString()} sections; this report does not establish corpus-wide coverage. ` : ""}${job.report_sections < job.total_sections || job.resume_phase ? 'Preliminary findings; research is incomplete.' : optimized ? 'All selected sections processed.' : 'All scoped sections processed.'} Citations link to evidence groups and their original excerpts. This is a model synthesis, not an authoritative ranking.`, 'scope-warning'),
    renderAnswer(report.answer, report.sources.length, 'research-source'));
  report.sources.forEach((source, index) => {
    const card = makeNode('section', '', 'source');
    card.id = 'research-source-' + (index + 1);
    card.tabIndex = -1;
    card.append(makeNode('h4', `${index + 1}. ${source.title} / ${source.heading}`), makeNode('p', source.text));
    const button = makeNode('button', 'Read underlying excerpts');
    button.type = 'button';
    let offset = 0;
    const excerpts = makeNode('div', '');
    button.addEventListener('click', async () => {
      button.disabled = true;
      try {
        const parameter = report.children_kind === 'finding' ? 'finding_id' : 'node_id';
        const data = await researchRequest('/' + job.id + '/findings?' + parameter + '=' + report.children[index] + '&limit=20&offset=' + offset);
        data.findings.forEach(finding => excerpts.append(researchFinding(finding, job.id)));
        offset += data.findings.length;
        button.textContent = offset < data.total ? `More excerpts · ${offset} / ${data.total}` : `All ${data.total} excerpts shown`;
        button.disabled = offset >= data.total;
      } catch (error) {
        excerpts.append(makeNode('p', error.message, 'error'));
        button.disabled = false;
      }
    });
    card.append(button, excerpts);
    container.append(card);
  });
}

async function refreshResearch() {
  if (!researchJob || researchBusy) return;
  researchBusy = true;
  try {
    const job = await researchRequest('/' + researchJob);
    if (job.id !== researchJob) return;
    element('research-progress').max = job.total_sections;
    element('research-progress').value = job.sections_examined;
    const seconds = job.active_seconds;
    const pace = job.batches ? Math.round(seconds / job.batches) : null;
    element('research-status').textContent = `${job.research_mode === "optimized" ? "Optimized research" : "Full scan"} · ${job.status} · ${job.phase} · ${job.sections_examined.toLocaleString()} / ${job.total_sections.toLocaleString()} sections examined (${job.coverage_percent}%) · ${job.partial_sections} partial · ${job.batches} source batches · ${job.summary_batches} summary batches · ${job.finding_count} excerpts · ${job.failures} failed runs. Scope: ${job.collection}, ${job.author}${job.book ? ', book: ' + job.book : ''}. ${pace === null ? '' : 'Recorded average: ' + pace + ' seconds per source batch, including report work.'} ${job.last_error}`;
    const decisions = job.selection_counts || {};
    element('research-selection-status').textContent = job.research_mode === 'optimized'
      ? `Round ${job.research_round + 1} of up to ${job.followup_rounds + 1} · ${decisions.pending || 0} candidates pending · ${decisions.selected || 0} selected · ${decisions.pruned || 0} below cutoff · ${job.summary_cache_sections || 0} reusable indexed summaries. Corpus coverage: ${job.corpus_coverage_percent}% of ${job.eligible_sections.toLocaleString()} eligible sections. Searches: ${(job.queries || []).join(' · ')}. ${job.stop_reason || ''}`
      : '';
    element('research-decisions').disabled = job.research_mode !== 'optimized';
    let eta = job.eta;
    // Older running servers can still show a rough section-based scan estimate.
    if (!eta) {
      const progress = job.sections_examined + job.partial_sections * 0.5;
      eta = job.status === 'complete' ? {seconds: 0, note: 'Complete.'} : job.phase === 'scan' && progress >= 3
        ? {seconds: seconds * (job.total_sections - progress) / progress, note: 'Rough scan estimate; final report time is additional and section lengths vary.'}
        : {seconds: null, note: 'Estimating after more progress.'};
    }
    const remaining = eta.seconds === null ? '' : eta.seconds === 0 ? '' :
      eta.seconds < 60 ? 'Less than a minute. ' : eta.seconds < 3600 ? `About ${Math.ceil(eta.seconds / 60)} minutes. ` :
      eta.seconds < 86400 ? `About ${(eta.seconds / 3600).toFixed(1)} hours. ` : `About ${(eta.seconds / 86400).toFixed(1)} days. `;
    element('research-eta').textContent = `Estimated time remaining${eta.target ? " (" + eta.target + ")" : ""}: ${remaining}${eta.note}`;
    element('research-summary-help').textContent = job.status === 'pausing'
      ? 'Pause requested. Waiting for the current model call to finish and save; summarizing will then be available.'
      : ['running', 'pausing'].includes(job.status)
        ? job.phase === 'report' ? 'Building the summary. Its report appears here when ready.' : 'Pause the scan first, then summarize the saved excerpts.'
        : !job.finding_count ? 'Summarizing needs at least one relevant excerpt. Resume the scan to collect evidence.'
        : 'Summarize findings so far is available. It uses saved excerpts; the full scan does not need to finish.';
    const active = ['running', 'pausing'].includes(job.status);
    element('research-pause').disabled = !active || job.status === 'pausing';
    element('research-resume').disabled = active || job.status === 'complete';
    element('research-summary').disabled = active || !job.finding_count;
    element('research-more').hidden = !job.finding_count || researchOffset >= job.finding_count;
    renderResearchReport(job);
  } catch (error) {
    element('research-status').textContent = error.message;
  } finally {
    researchBusy = false;
  }
}

async function loadResearchJobs(selected = '') {
  try {
    const data = await researchRequest('');
    element('research-jobs').replaceChildren();
    if (!data.jobs.length) element('research-jobs').append(makeNode('option', 'No saved jobs'));
    data.jobs.forEach(job => {
      const option = makeNode('option', job.question.slice(0, 90) + ' · ' + job.status);
      option.value = job.id;
      element('research-jobs').append(option);
    });
    researchJob = data.jobs.some(job => job.id === selected) ? selected : data.jobs[0]?.id || '';
    element('research-jobs').value = researchJob;
    researchOffset = 0;
    researchDecisionOffset = 0;
    researchDecisionTotal = 0;
    element('research-decision-list').replaceChildren();
    element('research-decisions').textContent = 'Show candidates and relevance scores';
    researchReportKey = '';
    element('research-findings').replaceChildren();
    await refreshResearch();
  } catch (error) {
    element('research-status').textContent = error.message;
  }
}

element('research-start').addEventListener('click', async () => {
  const button = element('research-start');
  button.disabled = true;
  try {
    const question = element('question').value.trim();
    if (!question) throw Error('Enter your research question above.');
    const job = await researchRequest('', {...researchSettings(), question, model: element('model').value,
      book: element('book').value, author: element('author').value, collection: element('collection').value,
      batch_words: Number(element('research-words').value), research_mode: element('research-mode').value,
      candidate_limit: Number(element('research-candidates').value), min_relevance: Number(element('research-relevance').value),
      followup_rounds: Number(element('research-rounds').value),
      answer_original: element('answer-original').checked, skip_wording_guidance: element('skip-wording-guidance').checked});
    await loadResearchJobs(job.id);
  } catch (error) {
    element('research-status').textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

element('research-jobs').addEventListener('change', () => loadResearchJobs(element('research-jobs').value));
for (const [button, action] of [['research-pause', 'pause'], ['research-resume', 'resume'], ['research-summary', 'report']]) {
  element(button).addEventListener('click', async () => {
    element(button).disabled = true;
    try {
      await researchRequest('/' + researchJob + '/' + action, researchSettings());
      await refreshResearch();
    } catch (error) {
      element('research-status').textContent = error.message;
    }
  });
}
element('research-more').addEventListener('click', async () => {
  try {
    const data = await researchRequest('/' + researchJob + '/findings?limit=20&offset=' + researchOffset);
    data.findings.forEach(finding => element('research-findings').append(researchFinding(finding, researchJob)));
    researchOffset += data.findings.length;
    element('research-more').textContent = `More collected excerpts · ${researchOffset} / ${data.total}`;
    element('research-more').hidden = researchOffset >= data.total;
  } catch (error) {
    element('research-status').textContent = error.message;
  }
});
element('research-decisions').addEventListener('click', async () => {
  try {
    if (researchDecisionTotal && researchDecisionOffset >= researchDecisionTotal) {
      researchDecisionOffset = 0;
      element('research-decision-list').replaceChildren();
    }
    const data = await researchRequest('/' + researchJob + '/selection?limit=20&offset=' + researchDecisionOffset);
    data.candidates.forEach(candidate => {
      const item = makeNode('p', `${candidate.title} / ${candidate.heading} · round ${candidate.round + 1} · ${candidate.origin} · ${candidate.state}${candidate.score === null ? '' : ' · relevance ' + candidate.score + '/3'}. ${candidate.reason || ''}`);
      element('research-decision-list').append(item);
    });
    researchDecisionTotal = data.total;
    researchDecisionOffset += data.candidates.length;
    element('research-decisions').textContent = researchDecisionOffset < data.total ? `More candidates · ${researchDecisionOffset} / ${data.total}` : `Refresh candidates · ${data.total} shown`;
  } catch (error) {
    element('research-selection-status').textContent = error.message;
  }
});
function researchModeHelp() {
  const optimized = element('research-mode').value === 'optimized';
  element('research-selection-settings').hidden = !optimized;
  element('research-mode-help').textContent = optimized
    ? 'Search reusable summaries and the word/meaning indexes, rate candidates, then read selected sections in full. Follow-up searches investigate gaps. The first run builds summaries; later runs reuse them. This does not read every book.'
    : 'Visit every stored section within your filters. It offers broader coverage but can take hours or days.';
}
element('research-mode').addEventListener('change', researchModeHelp);
researchModeHelp();
loadResearchJobs();
setInterval(() => {
  if (element('deep-research').open) refreshResearch();
}, 3000);
