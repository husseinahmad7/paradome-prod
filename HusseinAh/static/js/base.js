(function () {
    "use strict";

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".navbar-burger").forEach(function (toggle) {
            toggle.addEventListener("click", function () {
                const target = document.getElementById(toggle.dataset.target);
                if (!target) {
                    return;
                }

                const isActive = toggle.classList.toggle("is-active");
                target.classList.toggle("is-active", isActive);
                toggle.setAttribute("aria-expanded", String(isActive));
            });
        });

        let scrollbarTimer;
        window.addEventListener("scroll", function () {
            document.body.classList.add("on-scrollbar");
            window.clearTimeout(scrollbarTimer);
            scrollbarTimer = window.setTimeout(function () {
                document.body.classList.remove("on-scrollbar");
            }, 3000);
        }, { passive: true });
    });
})();
