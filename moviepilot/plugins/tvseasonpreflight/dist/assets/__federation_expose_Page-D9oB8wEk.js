import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,createVNode:_createVNode,createElementBlock:_createElementBlock} = await importShared('vue');


const _hoisted_1 = { class: "preflight-page" };
const _hoisted_2 = { class: "card-grid" };
const _hoisted_3 = { class: "card-head" };
const _hoisted_4 = { class: "card-value" };
const _hoisted_5 = { class: "count-value" };
const _hoisted_6 = { class: "count-value" };
const _hoisted_7 = { class: "count-value" };
const _hoisted_8 = {
  key: 0,
  class: "dialog-body"
};
const _hoisted_9 = {
  key: 1,
  class: "dialog-body"
};

const {computed,onMounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: { api: { type: Object, default: () => ({}) } },
  setup(__props) {

const props = __props;
const loading = ref(false);
const error = ref('');
const message = ref('');
const dialogOpen = ref(false);
const logTab = ref('success');
const state = ref({ installed: false, enabled: false, success_count: 0, skipped_count: 0, success_logs: [], skipped_logs: [], flow: '', path_mode: '' });
const totalLogs = computed(() => (state.value.success_count || 0) + (state.value.skipped_count || 0));
const logHeaders = [
  { title: '时间', key: 'date', width: 200 },
  { title: '处理结果', key: 'result', width: 120 },
  { title: '详细说明', key: 'message' },
];
const unwrap = response => response?.data?.data ?? response?.data ?? response;

async function loadStatus() {
  loading.value = true;
  try {
    const response = await props.api.post('plugin/TVSeasonPreflight/ui_status', {});
    state.value = unwrap(response) || state.value;
    error.value = '';
  } catch (err) { error.value = err?.message || '读取状态失败'; }
  finally { loading.value = false; }
}

async function toggleEngine(value) {
  loading.value = true;
  try {
    const response = await props.api.post('plugin/TVSeasonPreflight/toggle', { enabled: value });
    const body = response?.data ?? response;
    if (body?.success === false) error.value = body.message || '操作失败';
    else {
      message.value = body?.message || '设置已保存';
      if (body?.data) state.value = body.data;
    }
  } catch (err) { error.value = err?.message || '操作失败'; }
  finally { loading.value = false; }
}

function openLogs(tab) { logTab.value = tab; dialogOpen.value = true; }
onMounted(loadStatus);

return (_ctx, _cache) => {
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VSwitch = _resolveComponent("VSwitch");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VDialog = _resolveComponent("VDialog");

  return (_openBlock(), _createElementBlock("div", _hoisted_1, [
    (loading.value)
      ? (_openBlock(), _createBlock(_component_VProgressLinear, {
          key: 0,
          indeterminate: "",
          class: "mb-3"
        }))
      : _createCommentVNode("", true),
    (error.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 1,
          type: "error",
          variant: "tonal",
          closable: "",
          class: "mb-3"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(error.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    (message.value)
      ? (_openBlock(), _createBlock(_component_VAlert, {
          key: 2,
          type: "success",
          variant: "tonal",
          closable: "",
          class: "mb-3"
        }, {
          default: _withCtx(() => [
            _createTextVNode(_toDisplayString(message.value), 1)
          ]),
          _: 1
        }))
      : _createCommentVNode("", true),
    _createElementVNode("div", _hoisted_2, [
      _createVNode(_component_VCard, { class: "status-card card-status" }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _createElementVNode("div", _hoisted_3, [
                _cache[6] || (_cache[6] = _createElementVNode("span", null, "引擎状态", -1)),
                _createVNode(_component_VSwitch, {
                  "model-value": state.value.enabled,
                  color: "success",
                  "hide-details": "",
                  density: "compact",
                  disabled: !state.value.installed || loading.value,
                  "onUpdate:modelValue": toggleEngine
                }, null, 8, ["model-value", "disabled"])
              ]),
              _createElementVNode("div", _hoisted_4, _toDisplayString(state.value.installed ? (state.value.enabled ? '已启用' : '已停用') : '未安装'), 1),
              _cache[7] || (_cache[7] = _createElementVNode("div", { class: "card-note" }, "控制入库前自动分季", -1))
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, { class: "status-card card-flow" }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [...(_cache[8] || (_cache[8] = [
              _createElementVNode("div", { class: "card-label" }, "执行时机", -1),
              _createElementVNode("div", { class: "flow-text" }, "下载完成后、移动上传前", -1),
              _createElementVNode("div", { class: "card-note" }, "先核对 TMDB，再生成目标季度路径", -1)
            ]))]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "status-card card-success",
        onClick: _cache[0] || (_cache[0] = $event => (openLogs('success')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[9] || (_cache[9] = _createElementVNode("div", { class: "card-label" }, "自动分季成功", -1)),
              _createElementVNode("div", _hoisted_5, _toDisplayString(state.value.success_count || 0), 1),
              _cache[10] || (_cache[10] = _createElementVNode("div", { class: "card-note" }, "查看成功日志", -1)),
              _createVNode(_component_VIcon, {
                class: "arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "status-card card-skipped",
        onClick: _cache[1] || (_cache[1] = $event => (openLogs('skipped')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[11] || (_cache[11] = _createElementVNode("div", { class: "card-label" }, "安全跳过", -1)),
              _createElementVNode("div", _hoisted_6, _toDisplayString(state.value.skipped_count || 0), 1),
              _cache[12] || (_cache[12] = _createElementVNode("div", { class: "card-note" }, "总数不符、缺集或重复时不修改", -1)),
              _createVNode(_component_VIcon, {
                class: "arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "status-card card-logs",
        onClick: _cache[2] || (_cache[2] = $event => (openLogs('success')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[13] || (_cache[13] = _createElementVNode("div", { class: "card-label" }, "处理日志", -1)),
              _createElementVNode("div", _hoisted_7, _toDisplayString(totalLogs.value), 1),
              _cache[14] || (_cache[14] = _createElementVNode("div", { class: "card-note" }, "成功与安全跳过记录", -1)),
              _createVNode(_component_VIcon, {
                class: "arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _createVNode(_component_VAlert, {
      type: "info",
      variant: "tonal",
      class: "mt-4"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(state.value.flow), 1),
        _cache[15] || (_cache[15] = _createElementVNode("br", null, null, -1)),
        _createTextVNode(_toDisplayString(state.value.path_mode), 1),
        _cache[16] || (_cache[16] = _createElementVNode("br", null, null, -1)),
        _cache[17] || (_cache[17] = _createTextVNode("不会原地重命名做种文件；不满足严格条件时保持原任务不变。", -1))
      ]),
      _: 1
    }),
    _createVNode(_component_VDialog, {
      modelValue: dialogOpen.value,
      "onUpdate:modelValue": _cache[5] || (_cache[5] = $event => ((dialogOpen).value = $event)),
      "max-width": "1120",
      scrollable: ""
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "dialog-card" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, { class: "dialog-title" }, {
              default: _withCtx(() => [
                _cache[18] || (_cache[18] = _createElementVNode("span", null, "入库前分季日志", -1)),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  variant: "text",
                  onClick: _cache[3] || (_cache[3] = $event => (dialogOpen.value = false))
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider),
            _createVNode(_component_VTabs, {
              modelValue: logTab.value,
              "onUpdate:modelValue": _cache[4] || (_cache[4] = $event => ((logTab).value = $event)),
              class: "log-tabs"
            }, {
              default: _withCtx(() => [
                _createVNode(_component_VTab, { value: "success" }, {
                  default: _withCtx(() => [
                    _createTextVNode("成功日志（" + _toDisplayString(state.value.success_count || 0) + "）", 1)
                  ]),
                  _: 1
                }),
                _createVNode(_component_VTab, { value: "skipped" }, {
                  default: _withCtx(() => [
                    _createTextVNode("安全跳过（" + _toDisplayString(state.value.skipped_count || 0) + "）", 1)
                  ]),
                  _: 1
                })
              ]),
              _: 1
            }, 8, ["modelValue"]),
            _createVNode(_component_VDivider),
            (logTab.value === 'success')
              ? (_openBlock(), _createElementBlock("div", _hoisted_8, [
                  _createVNode(_component_VDataTable, {
                    headers: logHeaders,
                    items: state.value.success_logs,
                    "items-per-page": 20,
                    class: "data-table"
                  }, {
                    "item.result": _withCtx(() => [...(_cache[19] || (_cache[19] = [
                      _createElementVNode("span", { class: "success-text" }, "已自动分季", -1)
                    ]))]),
                    "no-data": _withCtx(() => [...(_cache[20] || (_cache[20] = [
                      _createElementVNode("div", { class: "empty" }, "暂无成功日志", -1)
                    ]))]),
                    _: 1
                  }, 8, ["items"])
                ]))
              : (_openBlock(), _createElementBlock("div", _hoisted_9, [
                  _createVNode(_component_VDataTable, {
                    headers: logHeaders,
                    items: state.value.skipped_logs,
                    "items-per-page": 20,
                    class: "data-table"
                  }, {
                    "item.result": _withCtx(() => [...(_cache[21] || (_cache[21] = [
                      _createElementVNode("span", { class: "skipped-text" }, "安全跳过", -1)
                    ]))]),
                    "no-data": _withCtx(() => [...(_cache[22] || (_cache[22] = [
                      _createElementVNode("div", { class: "empty" }, "暂无跳过日志", -1)
                    ]))]),
                    _: 1
                  }, 8, ["items"])
                ]))
          ]),
          _: 1
        })
      ]),
      _: 1
    }, 8, ["modelValue"])
  ]))
}
}

};
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-2b710cea"]]);

export { Page as default };
