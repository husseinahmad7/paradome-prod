(function () {
    "use strict";

    const root = document.documentElement;
    root.classList.add("js-ready");

    const nav = document.querySelector(".portfolio-nav");
    const navToggle = document.querySelector(".nav-toggle");
    const navLinks = Array.from(document.querySelectorAll("[data-nav-target]"));
    const progressBar = document.querySelector(".scroll-progress span");
    let progressFrame = 0;

    function setNavigationOpen(isOpen) {
        if (!nav || !navToggle) {
            return;
        }

        nav.dataset.open = String(isOpen);
        navToggle.setAttribute("aria-expanded", String(isOpen));
    }

    if (nav && navToggle) {
        setNavigationOpen(false);

        navToggle.addEventListener("click", function () {
            setNavigationOpen(nav.dataset.open !== "true");
        });

        document.addEventListener("keydown", function (event) {
            if (event.key === "Escape" && nav.dataset.open === "true") {
                setNavigationOpen(false);
                navToggle.focus();
            }
        });

        document.addEventListener("click", function (event) {
            if (nav.dataset.open === "true" && !nav.contains(event.target)) {
                setNavigationOpen(false);
            }
        });

        window.addEventListener("resize", function () {
            if (window.innerWidth > 820) {
                setNavigationOpen(false);
            }
        });
    }

    function focusHashTarget() {
        if (!window.location.hash) {
            return;
        }

        let id;
        try {
            id = decodeURIComponent(window.location.hash.slice(1));
        } catch (error) {
            return;
        }

        const target = document.getElementById(id);
        if (target) {
            target.focus({ preventScroll: true });
        }
    }

    document.querySelectorAll('a[href^="#"]').forEach(function (anchor) {
        anchor.addEventListener("click", function () {
            setNavigationOpen(false);
            window.setTimeout(focusHashTarget, 0);
        });
    });

    window.addEventListener("hashchange", focusHashTarget);
    if (window.location.hash) {
        window.setTimeout(focusHashTarget, 0);
    }

    function setActiveNavigation(id) {
        navLinks.forEach(function (link) {
            if (link.dataset.navTarget === id) {
                link.setAttribute("aria-current", "location");
            } else {
                link.removeAttribute("aria-current");
            }
        });
    }

    if ("IntersectionObserver" in window && navLinks.length) {
        const trackedSections = navLinks
            .map(function (link) {
                return document.getElementById(link.dataset.navTarget);
            })
            .filter(Boolean);

        const sectionObserver = new IntersectionObserver(function (entries) {
            const visible = entries
                .filter(function (entry) { return entry.isIntersecting; })
                .sort(function (a, b) { return b.intersectionRatio - a.intersectionRatio; });

            if (visible.length) {
                setActiveNavigation(visible[0].target.id);
            }
        }, {
            rootMargin: "-24% 0px -55%",
            threshold: [0.01, 0.15, 0.35]
        });

        trackedSections.forEach(function (section) {
            sectionObserver.observe(section);
        });
    }

    function updateProgress() {
        progressFrame = 0;
        if (!progressBar) {
            return;
        }

        const scrollable = root.scrollHeight - window.innerHeight;
        const progress = scrollable > 0 ? window.scrollY / scrollable : 0;
        progressBar.style.transform = "scaleX(" + Math.min(1, Math.max(0, progress)).toFixed(4) + ")";
    }

    function requestProgressUpdate() {
        if (!progressFrame) {
            progressFrame = window.requestAnimationFrame(updateProgress);
        }
    }

    updateProgress();
    window.addEventListener("scroll", requestProgressUpdate, { passive: true });
    window.addEventListener("resize", requestProgressUpdate);
})();
