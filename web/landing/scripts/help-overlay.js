/** Help overlay: hub navigation, FAQ accordion, and how-to carousel. */
let carouselIdx = 0;

document.getElementById('helpBtn').addEventListener('click', () => {
    showScreen('helpHub');
    document.getElementById('helpBackBtn').style.display = 'none';
    document.getElementById('helpTitle').textContent = 'Help';
    openOverlay('helpOverlay');
});

document.getElementById('helpCloseBtn').addEventListener('click', () => closeOverlay('helpOverlay'));

document.getElementById('helpBackBtn').addEventListener('click', () => {
    showScreen('helpHub');
    document.getElementById('helpBackBtn').style.display = 'none';
    document.getElementById('helpTitle').textContent = 'Help';
});

document.getElementById('goFaqBtn').addEventListener('click', () => {
    buildFaq();
    showScreen('helpFaq');
    document.getElementById('helpBackBtn').style.display = '';
    document.getElementById('helpTitle').textContent = 'Frequently Asked Questions';
});

document.getElementById('goHowToBtn').addEventListener('click', () => {
    buildCarousel();
    showScreen('helpHowTo');
    document.getElementById('helpBackBtn').style.display = '';
    document.getElementById('helpTitle').textContent = 'How to Use This Program';
});

function buildFaq() {
    const list = document.getElementById('faqList');
    if (list.children.length) return;

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
            list.querySelectorAll('.faq-item').forEach(i => i.classList.remove('open'));
            if (!isOpen) item.classList.add('open');
        });

        item.appendChild(btn);
        item.appendChild(ans);
        list.appendChild(item);
    });
}

function buildCarousel() {
    const track = document.getElementById('carouselTrack');
    const dots = document.getElementById('carouselDots');
    if (track.children.length) return;

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
    const dots = document.getElementById('carouselDots').querySelectorAll('.carousel-dot');
    carouselIdx = Math.max(0, Math.min(n, CAROUSEL_SLIDES.length - 1));
    track.style.transform = `translateX(-${carouselIdx * 100}%)`;
    dots.forEach((d, i) => d.classList.toggle('active', i === carouselIdx));
}

document.getElementById('carouselPrev').addEventListener('click', () => goToSlide(carouselIdx - 1));
document.getElementById('carouselNext').addEventListener('click', () => goToSlide(carouselIdx + 1));
