(function () {
    const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
        anchor.addEventListener('click', (event) => {
            const target = document.querySelector(anchor.getAttribute('href'));
            if (!target) {
                return;
            }

            event.preventDefault();
            target.scrollIntoView({
                behavior: prefersReducedMotion ? 'auto' : 'smooth',
                block: 'start'
            });

            const expandedNav = document.querySelector('.navbar-collapse.show');
            if (expandedNav && window.bootstrap) {
                window.bootstrap.Collapse.getOrCreateInstance(expandedNav).hide();
            }
        });
    });

    if (!prefersReducedMotion && 'IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach((entry) => {
                if (entry.isIntersecting) {
                    entry.target.classList.add('is-visible');
                    observer.unobserve(entry.target);
                }
            });
        }, { threshold: 0.16 });

        document.querySelectorAll('.portfolio-section, .project-card, .timeline-item').forEach((element) => {
            observer.observe(element);
        });
    }
})();
