// dsh-freecad — browser half of the FreeCAD DSH plugin.
//
// Contributes one page to DSH → Settings ("FreeCAD"): where the host half finds
// freecadcmd, plus the two places the program itself can be downloaded from.
// The field is the volatile `freecadPath` declared in index.js, so saving here
// re-applies this plugin's configuration and the next tool call uses the new
// executable without restarting DSH.
//
// Bundle format: a classic script that hands its factory to the client module
// loader; `require` reaches the platform modules (react) and any declared
// plugin bundle.
window.__ModuleLoader__.load({
  id: 'dsh-freecad',
  factory: (require) => {
    var module = { exports: {} }
    var exports = module.exports
    Object.defineProperty(exports, Symbol.toStringTag, { value: 'Module' })

    const React = require('react')
    const { jsx, jsxs } = require('react/jsx-runtime')

    /** Settings namespace: the Loader entry id of this plugin (index.js). */
    const ENTRY_NS = 'freecad'
    /** Dictionary namespace owned by this page. */
    const DICT_NS = 'settings.freecad'
    /** Field edited by the page; matches Config in index.js. */
    const FIELD = 'freecadPath'

    /** Official releases, where new versions are announced. */
    const OFFICIAL_URL = 'https://github.com/FreeCAD/FreeCAD/releases'
    /** Tsinghua TUNA mirror, the download page reachable from mainland China. */
    const MIRROR_URL = 'https://mirrors.tuna.tsinghua.edu.cn/github-release/FreeCAD/FreeCAD/FreeCAD%201.1.4/'

    const zh = {
      title: 'FreeCAD',
      description: '指定 dsh-freecad 调用的 FreeCAD 命令行程序。保存后立即生效，无需重启。',
      pathLabel: 'freecadcmd 路径',
      pathPlaceholder: 'D:/FreeCAD 1.1/bin/freecadcmd.exe',
      pathHint: '可填 freecadcmd.exe、FreeCAD 安装目录或 bin 目录；支持 %VAR% 与正斜杠。留空则按官方安装位置与 PATH 自动查找。',
      save: '保存',
      saving: '保存中…',
      saved: '已保存',
      reset: '恢复自动查找',
      discard: '放弃修改',
      saveFailed: '没有保存成功，请重试。',
      readOnly: '本部署的设置为只读。',
      linksLabel: '下载 FreeCAD',
      official: '官方 GitHub Releases',
      officialHint: 'github.com/FreeCAD/FreeCAD/releases',
      mirror: '清华 TUNA 镜像',
      mirrorHint: 'mirrors.tuna.tsinghua.edu.cn（国内可用）',
      note: '插件用 freecadcmd --version 探测版本，因此免安装的 7z 便携版同样可用。',
    }

    const en = {
      title: 'FreeCAD',
      description: 'The FreeCAD command-line program dsh-freecad runs. Changes apply to the next tool call; no restart needed.',
      pathLabel: 'freecadcmd path',
      pathPlaceholder: 'D:/FreeCAD 1.1/bin/freecadcmd.exe',
      pathHint: 'Accepts freecadcmd.exe, a FreeCAD install directory, or its bin directory; %VAR% and forward slashes work. Leave empty to search the usual install locations and PATH.',
      save: 'Save',
      saving: 'Saving…',
      saved: 'Saved',
      reset: 'Use automatic detection',
      discard: 'Discard changes',
      saveFailed: 'The deployment did not accept this value; it was left for you to correct.',
      readOnly: 'This deployment stores settings read-only.',
      linksLabel: 'Download FreeCAD',
      official: 'Official GitHub releases',
      officialHint: 'github.com/FreeCAD/FreeCAD/releases',
      mirror: 'Tsinghua TUNA mirror',
      mirrorHint: 'mirrors.tuna.tsinghua.edu.cn (from mainland China)',
      note: 'The plugin probes the build with freecadcmd --version, so the portable 7z distribution works as well as the installer.',
    }

    /** Inline styles built on the app's theme aliases, so both themes work. */
    const styles = {
      page: {
        display: 'flex',
        flexDirection: 'column',
        gap: '10px',
        maxWidth: '620px',
        color: 'var(--dsw-alias-label-primary)',
        fontSize: '13px',
        lineHeight: '1.6',
      },
      description: {
        margin: 0,
        color: 'var(--dsw-alias-label-secondary)',
      },
      label: {
        fontWeight: 600,
        color: 'var(--dsw-alias-label-primary)',
      },
      input: {
        boxSizing: 'border-box',
        width: '100%',
        padding: '7px 10px',
        borderRadius: '8px',
        border: '1px solid var(--dsw-alias-border-l2)',
        background: 'var(--dsw-specific-input-major)',
        color: 'var(--dsw-alias-label-primary)',
        font: 'inherit',
        fontFamily: 'ui-monospace, SFMono-Regular, Consolas, monospace',
        outline: 'none',
      },
      hint: {
        margin: 0,
        color: 'var(--dsw-alias-label-tertiary)',
        fontSize: '12px',
      },
      row: {
        display: 'flex',
        alignItems: 'center',
        gap: '8px',
        flexWrap: 'wrap',
      },
      primary: {
        padding: '6px 16px',
        borderRadius: '8px',
        border: '1px solid transparent',
        background: 'var(--dsw-alias-brand-primary)',
        color: 'var(--dsw-alias-label-primary-foreground)',
        font: 'inherit',
        fontSize: '13px',
        cursor: 'pointer',
      },
      ghost: {
        padding: '6px 14px',
        borderRadius: '8px',
        border: '1px solid var(--dsw-alias-border-l2)',
        background: 'transparent',
        color: 'var(--dsw-alias-label-primary)',
        font: 'inherit',
        fontSize: '13px',
        cursor: 'pointer',
      },
      disabled: {
        opacity: 0.5,
        cursor: 'default',
      },
      ok: {
        margin: 0,
        color: 'var(--dsw-alias-state-success-primary)',
        fontSize: '12px',
      },
      error: {
        margin: 0,
        color: 'var(--dsw-alias-state-danger-primary)',
        fontSize: '12px',
      },
      links: {
        display: 'flex',
        flexDirection: 'column',
        gap: '6px',
        marginTop: '6px',
        paddingTop: '10px',
        borderTop: '1px solid var(--dsw-alias-border-l2)',
      },
      link: {
        color: 'var(--dsw-alias-brand-primary)',
        textDecoration: 'none',
      },
      linkHint: {
        marginLeft: '8px',
        color: 'var(--dsw-alias-label-tertiary)',
        fontSize: '12px',
      },
    }

    /**
     * Read this page's string value out of one configuration layer.
     * @param layer - a settings layer, possibly missing.
     * @returns the string, or an empty string.
     */
    function readField(layer) {
      const value = layer && typeof layer === 'object' ? layer[FIELD] : undefined
      return typeof value === 'string' ? value : ''
    }

    /** Download row: a themed link plus the host it points at. */
    function DownloadLink(props) {
      return jsxs('div', {
        children: [
          jsx('a', {
            href: props.href,
            target: '_blank',
            rel: 'noreferrer noopener',
            style: styles.link,
            children: props.label,
          }),
          jsx('span', { style: styles.linkHint, children: props.hint }),
        ],
      })
    }

    /**
     * The Settings page: the freecadcmd path plus the two download links.
     * @param props - `t` from this page's dictionary and the shared config form.
     * @returns the page.
     */
    function FreeCadSection(props) {
      const t = props.t
      const form = props.form
      const subscribe = React.useCallback((listener) => form.subscribe(listener), [form])
      const snapshot = React.useSyncExternalStore(subscribe, () => form.getSnapshot())
      const [draft, setDraft] = React.useState(null)
      const [busy, setBusy] = React.useState(false)
      const [error, setError] = React.useState('')
      const [savedOnce, setSavedOnce] = React.useState(false)

      const loading = snapshot.status === 'loading'
      const readOnly = snapshot.writable === false
      const editable = !loading && !readOnly
      const saved = readField(snapshot.value) || readField(snapshot.base) || readField(snapshot.user)
      const value = draft === null ? saved : draft
      const dirty = draft !== null && draft.trim() !== saved

      /** Write one value through the Host, keeping the draft until it lands. */
      async function commit(next) {
        setBusy(true)
        setError('')
        setSavedOnce(false)
        try {
          const accepted = next === '' ? await form.unset(FIELD) : await form.set(FIELD, next)
          if (accepted) {
            setDraft(null)
            setSavedOnce(true)
          } else setError(t('saveFailed'))
        } catch (cause) {
          setError(cause && cause.message ? String(cause.message) : String(cause))
        } finally {
          setBusy(false)
        }
      }

      const dimmed = busy || !editable
      const buttonStyle = (extra) => ({ ...styles.ghost, ...extra, ...(dimmed ? styles.disabled : {}) })
      const saveStyle = { ...styles.primary, ...(dimmed || !dirty ? styles.disabled : {}) }

      return jsxs('div', {
        style: styles.page,
        children: [
          jsx('p', { style: styles.description, children: t('description') }),
          jsx('label', { style: styles.label, htmlFor: 'dsh-freecad-path', children: t('pathLabel') }),
          jsx('input', {
            id: 'dsh-freecad-path',
            type: 'text',
            spellCheck: false,
            autoComplete: 'off',
            style: styles.input,
            placeholder: t('pathPlaceholder'),
            value,
            disabled: !editable || busy,
            onChange: (event) => {
              setSavedOnce(false)
              setDraft(event.target.value)
            },
            onKeyDown: (event) => {
              if (event.key === 'Enter' && dirty) void commit(value.trim())
            },
          }),
          jsx('p', { style: styles.hint, children: t('pathHint') }),
          jsxs('div', {
            style: styles.row,
            children: [
              jsx('button', {
                type: 'button',
                style: saveStyle,
                disabled: busy || !editable || !dirty,
                onClick: () => void commit(value.trim()),
                children: busy ? t('saving') : savedOnce ? t('saved') : t('save'),
              }),
              jsx('button', {
                type: 'button',
                style: buttonStyle({}),
                disabled: busy || !editable || saved === '',
                onClick: () => void commit(''),
                children: t('reset'),
              }),
              draft === null ? null : jsx('button', {
                type: 'button',
                style: buttonStyle({}),
                disabled: busy,
                onClick: () => {
                  setDraft(null)
                  setSavedOnce(false)
                },
                children: t('discard'),
              }),
            ],
          }),
          readOnly ? jsx('p', { style: styles.hint, children: t('readOnly') }) : null,
          error ? jsx('p', { role: 'alert', style: styles.error, children: error }) : null,
          jsxs('div', {
            style: styles.links,
            children: [
              jsx('span', { style: styles.label, children: t('linksLabel') }),
              jsx(DownloadLink, { href: OFFICIAL_URL, label: t('official'), hint: t('officialHint') }),
              jsx(DownloadLink, { href: MIRROR_URL, label: t('mirror'), hint: t('mirrorHint') }),
              jsx('p', { style: styles.hint, children: t('note') }),
            ],
          }),
        ],
      })
    }

    /** Required services (cordis fiber inject). */
    const inject = ['slots', 'locale', 'configForms']

    /**
     * Mount the FreeCAD settings page once the Host serves its namespace.
     * @param ctx - the browser plugin context.
     */
    function apply(ctx) {
      const t = ctx.locale.bind(DICT_NS)
      ctx.effect(
        () => ctx.locale.register(DICT_NS, { zh, en }),
        'dsh-freecad: dictionaries',
      )
      ctx.effect(
        () => ctx.configForms.whileServed([ENTRY_NS], () => {
          const form = ctx.configForms.get(ENTRY_NS)
          return ctx.slots.inject('settings.section', () => ctx.slots.register({
            name: 'settings.section',
            id: 'freecad',
            order: 100,
            label: () => t('title'),
            locale: DICT_NS,
            inject: () => ({ t, form }),
          }, FreeCadSection))
        }),
        'dsh-freecad: settings page',
      )
    }

    exports.apply = apply
    exports.inject = inject
    return module.exports
  },
})
