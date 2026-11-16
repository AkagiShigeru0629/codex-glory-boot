(() => {
    const marker = "glory-boot-skin-style";
    const root = document.documentElement;
    const previousSkin = globalThis.__gloryBootSkin;
    if (previousSkin && typeof previousSkin.dispose === "function") {
        previousSkin.dispose();
    }

    const previousAttribute = root.getAttribute("data-glory-boot-skin");
    const propertyNames = ["--glory-boot-wallpaper", "--glory-boot-wash"];
    const previousProperties = new Map(
        propertyNames.map((name) => [
            name,
            [
                root.style.getPropertyValue(name),
                root.style.getPropertyPriority(name),
            ],
        ]),
    );
    const style = document.createElement("style");
    style.id = marker;
    style.textContent = __SKIN_CSS_JSON__;

    let wallpaperUrl = "";
    let disposed = false;
    const restoreProperty = (name, value, priority) => {
        if (value) {
            root.style.setProperty(name, value, priority);
        } else {
            root.style.removeProperty(name);
        }
    };
    const dispose = () => {
        if (disposed) {
            return false;
        }
        disposed = true;
        window.removeEventListener("keydown", onKeydown, true);
        style.remove();
        for (const [name, [value, priority]] of previousProperties) {
            restoreProperty(name, value, priority);
        }
        if (previousAttribute === null) {
            root.removeAttribute("data-glory-boot-skin");
        } else {
            root.setAttribute("data-glory-boot-skin", previousAttribute);
        }
        if (wallpaperUrl) {
            URL.revokeObjectURL(wallpaperUrl);
            wallpaperUrl = "";
        }
        if (globalThis.__gloryBootSkin?.dispose === dispose) {
            delete globalThis.__gloryBootSkin;
        }
        return true;
    };
    const onKeydown = (event) => {
        if (
            event.ctrlKey &&
            event.altKey &&
            event.shiftKey &&
            !event.metaKey &&
            event.code === "KeyR"
        ) {
            event.preventDefault();
            event.stopImmediatePropagation();
            dispose();
            root.setAttribute("data-glory-boot-skin-disabled", "true");
        }
    };

    try {
        const binary = atob(__WALLPAPER_BASE64_JSON__);
        const bytes = new Uint8Array(binary.length);
        for (let index = 0; index < binary.length; index += 1) {
            bytes[index] = binary.charCodeAt(index);
        }
        wallpaperUrl = URL.createObjectURL(
            new Blob([bytes], { type: __WALLPAPER_MIME_JSON__ }),
        );
        root.style.setProperty(
            "--glory-boot-wallpaper",
            `url("${wallpaperUrl}")`,
        );
        root.style.setProperty("--glory-boot-wash", "0.58");
        root.setAttribute("data-glory-boot-skin", "active");
        document.head.appendChild(style);
        window.addEventListener("keydown", onKeydown, true);
        globalThis.__gloryBootSkin = {
            installed: true,
            wallpaperUrl,
            dispose,
        };
        return { installed: true };
    } catch (error) {
        dispose();
        throw error;
    }
})()
