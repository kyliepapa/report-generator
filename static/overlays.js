// ============================================================
// overlays.js  — Help, Report & Request, Changelog, Dev Access
// Include via:  <script src="/static/overlays.js"></script>
// just before </body>, after script.js
// ============================================================

// ────────────────────────────────────────
// CONSTANTS
// ────────────────────────────────────────
const DEV_PASSWORD = 'aqua2026';   // ← change this

const FAQ_DATA = [
    {
        q: 'What is a Project ID and where do I find it?',
        a: 'CompanyCam is full of projects, & project names change all the time, so the program needs a more realiable way to search through the CompanyCam database & find the exact project you\'re looking for. It does that using the Project ID, a string of numbers unique to each project. You can find it in the URL of the project page, it is the only string of numbers in the URL. Just copy it over! If you can\'t find it, be sure you\'re on the project page, not another page like a report.'
    },
    {
        q: 'My project has a unit label format that doesn\'t fit any of the options, which do I click?',
        a: 'If identifying the location of the installation requires two tags, like a unit & building, click either 123 A or A 123. If it only takes one tag to determine location, click 123. All of the buttons are set up to handle a certain set of unusual cases. Give it a try & let me know if it doesn\'t work so I can add that special case. More info on How-To Slide 2.'
    },
    {
        q: 'Things are all over the place & wrong in the report, what happened & what do I do?',
        a: 'Don\'t worry! The thing about automation is that when something goes wrong, it often offsets the whole program. Some things to check that may be throwing your report out of whack: First, check the tags on the offending photos. The most common cause of misplaced photos is incorrect or incomplete tagging. Simply adjust the tags as needed on CompanyCam & rerun the program. Second, check your inputs on the landing page, such as the spelling of your Bathroom Inputs & if you cliked the right format option. Remember to use the How-To Walkthrough as a resource, and if things still aren\'t working, let me know.'
    },
    {
        q: 'What are some random fun facts about programming?',
        a: 'The first ever computer programmer was a woman named Ada Lovelace, botn in 1815. The first computer "bug" was a literal moth found inside a computer in 1947, that is where the term comes from. There are over 700 coding languages, yet 60-70% of projects use the top five most popular languages. The popular language JavaScript was formulated in only 10 days, & the popular language Python was not named after the snake, but after Monty Python.'
    },
    {
        q: 'What are some random specs of this program?',
        a: 'This program is written using four languages: Python (Flask), HTML, CSS, & JavaScript. It also relies on multiple fluctuating text files, which provide & store important data. Not counting those text files, this program contains over 7,000 lines of code spread across about seven files. The program\'s heaviest task is generating the pdf report, though the feature that took the longest to code was actually the original sorting algorithm that the whole program would end up being based upon.'
    },
    {
        q: 'Why did the above FAQs have nothing to do with how to use this program?',
        a: 'I coded in space for 6 FAQs expecting to only have a few to start, because the others will be filled in as I received questions & figure out what is legitimately being frequently asked. As the developer, I am way too familiar with my own program to know exactly what little thing might confuse a user. So these last three FAQs are just placeholders until I have enough data.'
    },
];

const CAROUSEL_SLIDES = [
    { 
        label: 'Step 1 — Input page', 
        image: '/static/images/step1.png', 
        note: 'Tip: You don\'t need to sift through your photos to find these inputs, just read through the tag list at the top of the project page in CompanyCam' 
    },
    { 
        label: 'Step 2 — Input page cont.', 
        image: '/static/images/step2.png', 
        note: 'Tip: Check your spelling, a misspelled input can throw the program for a loop.' 
    },
    { 
        label: 'Step 3 — Understanding the Terminal', 
        image: '/static/images/step3.png', 
        note: 'Fun Fact: All of the text updates as the program fetches tags may seem excessive, but it actually keeps the connection alive.' 
    },
    { 
        label: 'Step 4 — Navigating the Internal Report', 
        image: '/static/images/step4.png', 
        note: 'Tip: If you see weirdly placed photos or photos in "Unassigned" section, check your tags. That is how you can tell a photo isn\'t tagged properly in CompanyCam' 
    },
    { 
        label: 'Step 5 — Manually Re-arranging Photos', 
        image: '/static/images/step5.png', 
        note: 'Fun Fact: You know how when you drag things to the edge of the screen, it scrolls? That had to be programmed separately, it\'s not built in to drag & drop systems'
    },
    { 
        label: 'Step 6 — Customizing Layout', 
        image: '/static/images/step6.png', 
        note: 'Tip: Don\'t worry that "Hide Empty Fields" disappears when you select the Linear layout, it\'s just built in to that layout.' 
    },
    { 
        label: 'Step 7 — Customizing Cover Page', 
        image: '/static/images/step7.png', 
        note: '' 
    },
    { 
        label: 'Step 8 — Photo Visibility Control', 
        image: '/static/images/step8.png', 
        note: '' 
    },
    { 
        label: 'Step 9 — Generate PDF', 
        image: '/static/images/step9.png', 
        note: '' 
    },
    { 
        label: 'Step 10 — Finished Product!', 
        image: '/static/images/step10.png', 
        note: 'Enjoy your polished pdf report!' 
    },
];


// ────────────────────────────────────────
// OVERLAY OPEN / CLOSE HELPERS
// ────────────────────────────────────────
function openOverlay(id) {
    document.getElementById(id).classList.add('open');
}

function closeOverlay(id) {
    document.getElementById(id).classList.remove('open');
}

// Close on backdrop click (not panel click)
['helpOverlay', 'rnrOverlay', 'changelogOverlay', 'devOverlay'].forEach(id => {
    document.getElementById(id).addEventListener('click', function (e) {
        if (e.target === this) closeOverlay(id);
    });
});

// ESC key closes any open overlay
document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        ['helpOverlay', 'rnrOverlay', 'changelogOverlay', 'devOverlay'].forEach(closeOverlay);
    }
});


// ────────────────────────────────────────
// SCREEN SWITCHER HELPER
// ────────────────────────────────────────
function showScreen(screenId) {
    const panel = document.getElementById(screenId).closest('.overlay-panel');
    panel.querySelectorAll('.overlay-screen').forEach(s => s.classList.remove('active'));
    document.getElementById(screenId).classList.add('active');
}


// ════════════════════════════════════════
// HELP OVERLAY
// ════════════════════════════════════════
document.getElementById('helpBtn').addEventListener('click', () => {
    showScreen('helpHub');
    document.getElementById('helpBackBtn').style.display = 'none';
    document.getElementById('helpTitle').textContent = 'Help';
    openOverlay('helpOverlay');
});

document.getElementById('helpCloseBtn').addEventListener('click', () => closeOverlay('helpOverlay'));

// Back button
document.getElementById('helpBackBtn').addEventListener('click', () => {
    showScreen('helpHub');
    document.getElementById('helpBackBtn').style.display = 'none';
    document.getElementById('helpTitle').textContent = 'Help';
});

// ── Go to FAQ ──
document.getElementById('goFaqBtn').addEventListener('click', () => {
    buildFaq();
    showScreen('helpFaq');
    document.getElementById('helpBackBtn').style.display = '';
    document.getElementById('helpTitle').textContent = 'Frequently Asked Questions';
});

// ── Go to How To ──
document.getElementById('goHowToBtn').addEventListener('click', () => {
    buildCarousel();
    showScreen('helpHowTo');
    document.getElementById('helpBackBtn').style.display = '';
    document.getElementById('helpTitle').textContent = 'How to Use This Program';
});

// ── Build FAQ ──
function buildFaq() {
    const list = document.getElementById('faqList');
    if (list.children.length) return; // already built

    FAQ_DATA.forEach(({ q, a }) => {
        const item = document.createElement('div');
        item.className = 'faq-item';

        const btn = document.createElement('button');
        btn.className = 'faq-question';
        btn.innerHTML = `<span>${q}</span><span class="faq-chevron">▼</span>`;

        const ans = document.createElement('div');
        ans.className = 'faq-answer';
        ans.textContent = a;

        btn.addEventListener('click', () => {
            const isOpen = item.classList.contains('open');
            // Close all
            list.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));
            if (!isOpen) item.classList.add('open');
        });

        item.appendChild(btn);
        item.appendChild(ans);
        list.appendChild(item);
    });
}

// ── Build carousel ──
let carouselIdx = 0;

function buildCarousel() {
    const track = document.getElementById('carouselTrack');
    const dots  = document.getElementById('carouselDots');
    if (track.children.length) return; // already built

    CAROUSEL_SLIDES.forEach((slide, i) => {
        const el = document.createElement('div');
        el.className = 'carousel-slide';
        el.innerHTML = `
            <img src="${slide.image}" alt="${slide.label}">
            <div style="font-size:15px;font-weight:600;color:var(--text);text-align:center;flex-shrink:0;">
                ${slide.label}
            </div>
            ${slide.note ? `<div style="font-size:13px;color:var(--muted);text-align:center;line-height:1.6;max-width:560px;flex-shrink:0;">${slide.note}</div>` : ''}
            <div class="carousel-slide-label">${i + 1} / ${CAROUSEL_SLIDES.length}</div>
        `;
        track.appendChild(el);

        const dot = document.createElement('div');
        dot.className = 'carousel-dot' + (i === 0 ? ' active' : '');
        dot.addEventListener('click', () => goToSlide(i));
        dots.appendChild(dot);
    });

    carouselIdx = 0;
}

function goToSlide(n) {
    const track = document.getElementById('carouselTrack');
    const dots  = document.getElementById('carouselDots').querySelectorAll('.carousel-dot');
    carouselIdx = Math.max(0, Math.min(n, CAROUSEL_SLIDES.length - 1));
    track.style.transform = `translateX(-${carouselIdx * 100}%)`;
    dots.forEach((d, i) => d.classList.toggle('active', i === carouselIdx));
}

document.getElementById('carouselPrev').addEventListener('click', () => goToSlide(carouselIdx - 1));
document.getElementById('carouselNext').addEventListener('click', () => goToSlide(carouselIdx + 1));


// ════════════════════════════════════════
// REPORT & REQUEST OVERLAY
// ════════════════════════════════════════
document.getElementById('rnrBtn').addEventListener('click', () => {
    showScreen('rnrForm');
    document.getElementById('rnrError').textContent = '';
    openOverlay('rnrOverlay');
});

document.getElementById('rnrCloseBtn').addEventListener('click', () => closeOverlay('rnrOverlay'));

document.getElementById('rnrSubmitBtn').addEventListener('click', async () => {
    const message   = document.getElementById('rnrMessage').value.trim();
    const submitter = document.getElementById('rnrSubmitter').value.trim();
    const errorEl   = document.getElementById('rnrError');

    if (!message && !submitter) {
        errorEl.textContent = 'Please fill in both fields before submitting.';
        return;
    }
    if (!message) {
        errorEl.textContent = 'Please describe your report or request.';
        return;
    }
    if (!submitter) {
        errorEl.textContent = 'Please enter your name in the "Submitted by" field.';
        return;
    }

    errorEl.textContent = '';

    try {
        const res = await fetch('/submit_rnr', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, submitter }),
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);

        // Clear fields
        document.getElementById('rnrMessage').value   = '';
        document.getElementById('rnrSubmitter').value = '';

        // Show success, then auto-close after 2.4s
        showScreen('rnrSuccess');
        setTimeout(() => closeOverlay('rnrOverlay'), 2400);
    } catch (err) {
        errorEl.textContent = `Submission failed: ${err.message}`;
    }
});


// ════════════════════════════════════════
// CHANGELOG OVERLAY
// ════════════════════════════════════════
document.getElementById('changelogBtn').addEventListener('click', async () => {
    const content = document.getElementById('changelogContent');
    content.textContent = 'Loading…';
    openOverlay('changelogOverlay');

    try {
        const res = await fetch('/get_changelog');
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        if (data.content && data.content.trim()) {
            content.textContent = data.content;
        } else {
            content.innerHTML = '<div class="changelog-empty">No changelog entries yet.</div>';
        }
    } catch (err) {
        content.innerHTML = `<div class="changelog-empty">Could not load changelog: ${err.message}</div>`;
    }
});

document.getElementById('changelogCloseBtn').addEventListener('click', () => closeOverlay('changelogOverlay'));


// ════════════════════════════════════════
// DEV ACCESS OVERLAY
// ════════════════════════════════════════
let devUnlocked = false;

document.getElementById('devBtn').addEventListener('click', () => {
    if (devUnlocked) {
        showScreen('devHub');
        document.getElementById('devBackBtn').style.display = 'none';
        document.getElementById('devTitle').textContent = 'Developer Access';
    } else {
        showScreen('devPwScreen');
        document.getElementById('devBackBtn').style.display = 'none';
        document.getElementById('devTitle').textContent = 'Developer Access';
        document.getElementById('devPwInput').value = '';
        document.getElementById('devPwError').textContent = '';
    }
    openOverlay('devOverlay');
});

document.getElementById('devCloseBtn').addEventListener('click', () => {
    // Auto-save any open editor before closing
    autoSaveDevEditors();
    closeOverlay('devOverlay');
});

// Allow closing dev overlay via backdrop (save first)
document.getElementById('devOverlay').addEventListener('click', function (e) {
    if (e.target === this) {
        autoSaveDevEditors();
        closeOverlay('devOverlay');
    }
});

document.getElementById('devPwSubmit').addEventListener('click', checkDevPassword);
document.getElementById('devPwInput').addEventListener('keydown', e => {
    if (e.key === 'Enter') checkDevPassword();
});

function checkDevPassword() {
    const val = document.getElementById('devPwInput').value;
    if (val === DEV_PASSWORD) {
        devUnlocked = true;
        document.getElementById('devPwError').textContent = '';
        showScreen('devHub');
        document.getElementById('devBackBtn').style.display = 'none';
        document.getElementById('devTitle').textContent = 'Developer Access';
    } else {
        document.getElementById('devPwError').textContent = 'Incorrect password.';
        document.getElementById('devPwInput').value = '';
        document.getElementById('devPwInput').focus();
    }
}

// Back button
document.getElementById('devBackBtn').addEventListener('click', () => {
    autoSaveDevEditors();
    showScreen('devHub');
    document.getElementById('devBackBtn').style.display = 'none';
    document.getElementById('devTitle').textContent = 'Developer Access';
});

// ── Go to Usage Logs ──
document.getElementById('goUsageLogsBtn').addEventListener('click', async () => {
    showScreen('devUsageLogs');
    document.getElementById('devBackBtn').style.display = '';
    document.getElementById('devTitle').textContent = 'Usage Logs';

    const area = document.getElementById('devUsageLogsArea');
    area.value = 'Loading…';
    try {
        const res = await fetch('/dev_get_file?file=usage_logs');
        const data = await res.json();
        area.value = data.content || '';
    } catch (err) {
        area.value = `Error loading file: ${err.message}`;
    }
});

// ── Go to Reports & Requests ──
document.getElementById('goDevRnrBtn').addEventListener('click', async () => {
    showScreen('devRnrEditor');
    document.getElementById('devBackBtn').style.display = '';
    document.getElementById('devTitle').textContent = 'Reports & Requests';

    const area = document.getElementById('devRnrArea');
    area.value = 'Loading…';
    try {
        const res = await fetch('/dev_get_file?file=repnreq');
        const data = await res.json();
        area.value = data.content || '';
    } catch (err) {
        area.value = `Error loading file: ${err.message}`;
    }
});

// ── Save buttons ──
document.getElementById('devSaveUsage').addEventListener('click', () => saveDevFile('usage_logs', 'devUsageLogsArea', 'devSaveUsageFlash'));
document.getElementById('devSaveRnr').addEventListener('click',   () => saveDevFile('repnreq',    'devRnrArea',        'devSaveRnrFlash'));

async function saveDevFile(file, areaId, flashId) {
    const content = document.getElementById(areaId).value;
    try {
        await fetch('/dev_save_file', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ file, content }),
        });
        const flash = document.getElementById(flashId);
        flash.classList.add('show');
        setTimeout(() => flash.classList.remove('show'), 2000);
    } catch (err) {
        console.error('Save failed:', err);
    }
}

function autoSaveDevEditors() {
    const usageScreen = document.getElementById('devUsageLogs');
    const rnrScreen   = document.getElementById('devRnrEditor');
    if (usageScreen.classList.contains('active')) {
        saveDevFile('usage_logs', 'devUsageLogsArea', 'devSaveUsageFlash');
    }
    if (rnrScreen.classList.contains('active')) {
        saveDevFile('repnreq', 'devRnrArea', 'devSaveRnrFlash');
    }
}