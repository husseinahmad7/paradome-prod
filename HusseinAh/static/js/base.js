(function () {
    "use strict";

    let lastDialogTrigger = null;
    const boundChatPanels = new WeakSet();
    const boundModals = new WeakSet();

    function closeModal(modal) {
        if (!modal) {
            return;
        }
        const trigger = modal.dialogTrigger;
        modal.remove();
        if (!document.querySelector(".modal.is-active")) {
            document.documentElement.classList.remove("is-clipped");
        }
        if (trigger && trigger.isConnected) {
            trigger.focus();
        }
    }

    function initModals(root) {
        const modals = [];
        if (root.matches && root.matches(".modal[role=dialog]")) {
            modals.push(root);
        }
        if (root.querySelectorAll) {
            root.querySelectorAll(".modal[role=dialog]").forEach(function (modal) {
                modals.push(modal);
            });
        }

        modals.forEach(function (modal) {
            if (boundModals.has(modal)) {
                return;
            }
            boundModals.add(modal);
            modal.dialogTrigger = lastDialogTrigger;
            lastDialogTrigger = null;
            document.documentElement.classList.add("is-clipped");

            modal.querySelectorAll(".js-close-replies").forEach(function (control) {
                control.addEventListener("click", function () {
                    closeModal(modal);
                });
            });

            modal.addEventListener("keydown", function (event) {
                if (event.key !== "Tab") {
                    return;
                }
                const focusable = Array.from(
                    modal.querySelectorAll(
                        "a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex='-1'])"
                    )
                ).filter(function (element) {
                    return element.getAttribute("aria-hidden") !== "true";
                });
                if (!focusable.length) {
                    event.preventDefault();
                    return;
                }
                const first = focusable[0];
                const last = focusable[focusable.length - 1];
                if (event.shiftKey && document.activeElement === first) {
                    event.preventDefault();
                    last.focus();
                } else if (!event.shiftKey && document.activeElement === last) {
                    event.preventDefault();
                    first.focus();
                }
            });

            window.requestAnimationFrame(function () {
                const initialFocus = modal.querySelector(".modal-card-head .js-close-replies");
                if (initialFocus) {
                    initialFocus.focus();
                }
            });
        });
    }

    function disconnectChat(panel) {
        if (!panel) {
            return;
        }
        if (panel.chatConnectionFallback) {
            window.clearTimeout(panel.chatConnectionFallback);
            panel.chatConnectionFallback = null;
        }
        if (panel.chatPusher) {
            panel.chatPusher.disconnect();
            panel.chatPusher = null;
        }
    }

    function disconnectChats(root) {
        const panels = [];
        if (root && root.matches && root.matches(".chat-panel")) {
            panels.push(root);
        }
        if (root && root.querySelectorAll) {
            root.querySelectorAll(".chat-panel").forEach(function (panel) {
                panels.push(panel);
            });
        }
        panels.forEach(disconnectChat);
    }

    function canonicalPath(value) {
        try {
            const path = new URL(value, window.location.href).pathname;
            return path === "/" ? path : path.replace(/\/+$/, "");
        } catch (error) {
            return "";
        }
    }

    function navigationUrlFor(source) {
        if (!source || !source.getAttribute) {
            return window.location.href;
        }
        const pushedUrl = source.getAttribute("hx-push-url");
        if (pushedUrl && pushedUrl !== "true") {
            return pushedUrl;
        }
        return source.getAttribute("hx-get")
            || source.getAttribute("href")
            || source.getAttribute("action")
            || window.location.href;
    }

    function syncDomeNavigation(value) {
        const requestedPath = canonicalPath(value);
        if (!requestedPath) {
            return;
        }
        document.querySelectorAll(
            ".dome-nav-link[href], .channel-link[href]"
        ).forEach(function (link) {
            if (canonicalPath(link.getAttribute("href")) === requestedPath) {
                link.setAttribute("aria-current", "page");
            } else {
                link.removeAttribute("aria-current");
            }
        });
    }

    function initChat(root) {
        const panels = root.querySelectorAll ? root.querySelectorAll(".chat-panel") : [];
        panels.forEach(function (panel) {
            if (boundChatPanels.has(panel)) {
                return;
            }

            const channelId = Number(panel.dataset.channelId);
            const log = panel.querySelector(".chat-log");
            const form = panel.querySelector(".chat-composer");
            const status = panel.querySelector(".realtime-status");
            if (!Number.isSafeInteger(channelId) || !log || !form || !status) {
                return;
            }
            boundChatPanels.add(panel);

            log.scrollTop = log.scrollHeight;
            form.addEventListener("htmx:beforeRequest", function () {
                form.setAttribute("aria-busy", "true");
            });
            log.addEventListener("htmx:beforeSwap", function (event) {
                const markup = event.detail.serverResponse
                    || (event.detail.xhr && event.detail.xhr.responseText)
                    || "";
                if (!markup) {
                    return;
                }
                const fragment = document.createElement("template");
                fragment.innerHTML = markup;
                const incoming = fragment.content.querySelector(".chat-message[id]");
                if (incoming && document.getElementById(incoming.id)) {
                    event.detail.shouldSwap = false;
                }
            });
            form.addEventListener("htmx:afterRequest", function (event) {
                form.removeAttribute("aria-busy");
                if (!event.detail.successful) {
                    return;
                }
                form.reset();
                const empty = log.querySelector("#empty-chat");
                if (empty) {
                    empty.remove();
                }
                log.scrollTop = log.scrollHeight;
            });
            log.addEventListener("htmx:afterRequest", function (event) {
                if (!event.detail.successful) {
                    return;
                }
                const source = event.detail.elt
                    || (event.detail.requestConfig && event.detail.requestConfig.elt);
                const control = source && source.closest(".chat-history-control");
                if (control && log.contains(control)) {
                    control.remove();
                }
            });
            log.addEventListener("htmx:afterSwap", function () {
                const empty = log.querySelector("#empty-chat");
                if (empty && log.querySelector(".chat-message")) {
                    empty.remove();
                }
                log.scrollTop = log.scrollHeight;
            });

            const csrfInput = form.querySelector("input[name=csrfmiddlewaretoken]");
            if (
                !panel.dataset.pusherKey
                || !panel.dataset.pusherCluster
                || !csrfInput
                || typeof window.Pusher === "undefined"
            ) {
                status.textContent = "Saved messages";
                return;
            }

            try {
                status.textContent = "Connecting";
                const connectionFallback = window.setTimeout(function () {
                    if (status.textContent === "Connecting") {
                        status.textContent = "Saved messages";
                    }
                }, 6000);
                panel.chatConnectionFallback = connectionFallback;
                const pusher = new window.Pusher(panel.dataset.pusherKey, {
                    cluster: panel.dataset.pusherCluster,
                    authEndpoint: panel.dataset.authUrl,
                    auth: { headers: { "X-CSRFToken": csrfInput.value } }
                });
                panel.chatPusher = pusher;
                pusher.connection.bind("connected", function () {
                    window.clearTimeout(connectionFallback);
                    status.textContent = "Realtime ready";
                });
                pusher.connection.bind("unavailable", function () {
                    window.clearTimeout(connectionFallback);
                    status.textContent = "Saved messages";
                });
                pusher.connection.bind("error", function () {
                    status.textContent = "Saved messages";
                });

                const channel = pusher.subscribe(panel.dataset.privateChannel);
                channel.bind("message-created", function (data) {
                    const messageId = Number(data && data.message_id);
                    const activeLog = document.getElementById("messages-" + channelId);
                    if (
                        !activeLog
                        || !Number.isSafeInteger(messageId)
                        || Number(data.channel_id) !== channelId
                        || document.getElementById("message-" + messageId)
                    ) {
                        return;
                    }
                    if (window.htmx) {
                        const fragmentUrl = panel.dataset.fragmentUrl.replace(
                            "/0/",
                            "/" + messageId + "/"
                        );
                        window.htmx.ajax("GET", fragmentUrl, {
                            target: "#messages-" + channelId,
                            swap: "beforeend"
                        });
                    }
                    const empty = activeLog.querySelector("#empty-chat");
                    if (empty) {
                        empty.remove();
                    }
                    activeLog.scrollTop = activeLog.scrollHeight;
                });
            } catch (error) {
                status.textContent = "Saved messages";
            }
        });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll(".navbar-burger").forEach(function (toggle) {
            const target = document.getElementById(toggle.dataset.target);
            if (!target) {
                return;
            }

            const setOpen = function (isOpen) {
                toggle.classList.toggle("is-active", isOpen);
                target.classList.toggle("is-active", isOpen);
                toggle.setAttribute("aria-expanded", String(isOpen));
                toggle.setAttribute(
                    "aria-label",
                    isOpen ? "Close navigation" : "Open navigation"
                );
            };

            toggle.addEventListener("click", function () {
                setOpen(toggle.getAttribute("aria-expanded") !== "true");
            });

            document.addEventListener("keydown", function (event) {
                if (
                    event.key === "Escape"
                    && toggle.getAttribute("aria-expanded") === "true"
                ) {
                    setOpen(false);
                    toggle.focus();
                }
            });

            document.addEventListener("click", function (event) {
                if (
                    toggle.getAttribute("aria-expanded") === "true"
                    && !target.contains(event.target)
                    && !toggle.contains(event.target)
                ) {
                    setOpen(false);
                }
            });
        });

        initChat(document);
        initModals(document);
        syncDomeNavigation(window.location.href);

        document.body.addEventListener("htmx:beforeRequest", function (event) {
            const source = event.detail.elt;
            if (source && source.matches && source.matches("[aria-haspopup='dialog']")) {
                lastDialogTrigger = source;
            }
            const target = event.detail.target;
            if (target && target.id === "main-content") {
                target.setAttribute("aria-busy", "true");
            }
        });

        document.body.addEventListener("htmx:beforeSwap", function (event) {
            const target = event.detail.target;
            if (!target || target.id !== "main-content") {
                return;
            }
            disconnectChats(target);
        });

        document.body.addEventListener("htmx:beforeCleanupElement", function (event) {
            disconnectChats(event.detail.elt);
        });

        document.body.addEventListener("htmx:beforeHistorySave", function () {
            disconnectChats(document);
        });

        document.body.addEventListener("htmx:afterRequest", function (event) {
            const target = event.detail.target;
            if (target && target.id === "main-content") {
                target.removeAttribute("aria-busy");
            }
        });

        document.body.addEventListener("htmx:afterSwap", function (event) {
            const target = event.detail.target;
            initModals(target || document);
            if (!target || target.id !== "main-content") {
                return;
            }

            const source = event.detail.requestConfig && event.detail.requestConfig.elt;
            syncDomeNavigation(navigationUrlFor(source));
            initChat(target);
            target.focus({ preventScroll: true });
        });

        document.body.addEventListener("htmx:historyRestore", function () {
            initChat(document);
            initModals(document);
            syncDomeNavigation(window.location.href);
        });

        document.addEventListener("keydown", function (event) {
            if (event.key !== "Escape") {
                return;
            }
            const modal = document.querySelector(".modal.is-active");
            if (modal) {
                closeModal(modal);
            }
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
