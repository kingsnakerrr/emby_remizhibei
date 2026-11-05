import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createElementVNode:_createElementVNode,createVNode:_createVNode,normalizeClass:_normalizeClass,createElementBlock:_createElementBlock,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "season-page" };
const _hoisted_2 = { class: "dashboard-grid" };
const _hoisted_3 = { class: "card-value" };
const _hoisted_4 = { class: "card-note" };
const _hoisted_5 = { class: "card-value" };
const _hoisted_6 = { class: "card-value" };
const _hoisted_7 = { class: "card-note" };
const _hoisted_8 = { class: "card-value" };
const _hoisted_9 = { class: "card-note" };
const _hoisted_10 = { class: "actions my-4" };
const _hoisted_11 = {
  key: 0,
  class: "table-actions"
};
const _hoisted_12 = ["title"];
const _hoisted_13 = { class: "dialog-body" };
const _hoisted_14 = { class: "dialog-body" };
const _hoisted_15 = { class: "dialog-body" };
const _hoisted_16 = { class: "dialog-body" };
const _hoisted_17 = { class: "dialog-body" };

const {computed,onMounted,onUnmounted,ref} = await importShared('vue');



const _sfc_main = {
  __name: 'Page',
  props: { api: { type: Object, default: () => ({}) } },
  setup(__props) {

const props = __props;
const loading = ref(false);
const message = ref('');
const error = ref('');
const dialog = ref('');
const recordTab = ref('scan');
const scanSearch = ref('');
const state = ref({
  headline: '正在读取状态…', summary: {}, scan_results: [], active_jobs: [],
  success_jobs: [], failed_jobs: [], scan_logs: [], other_logs: [], actions: [],
});
let timer;

const summary = computed(() => state.value.summary || {});
const dialogOpen = computed({
  get: () => Boolean(dialog.value),
  set: value => { if (!value) dialog.value = ''; },
});
const unwrap = response => response?.data?.data ?? response?.data ?? response;
const formatDuration = row => row?.duration_seconds === undefined ? '—' : `${row.duration_seconds} 秒`;
const scanHeaders = [
  { title: '媒体', key: 'name' },
  { title: '当前季度', key: 'current_summary', width: 230 },
  { title: 'TMDB 季度', key: 'official_summary', width: 230 },
  { title: '判断', key: 'status', width: 150 },
  { title: '操作', key: 'actions', sortable: false, width: 170 },
];
const jobHeaders = [
  { title: '媒体', key: 'name' },
  { title: '开始时间', key: 'started_at', width: 190 },
  { title: '结束时间', key: 'finished_at', width: 190 },
  { title: '耗时', key: 'duration', width: 100 },
  { title: '结果', key: 'message' },
];
const operationHeaders = [
  { title: '任务', key: 'title', width: 190 },
  { title: '开始时间', key: 'started_at', width: 190 },
  { title: '结束时间', key: 'finished_at', width: 190 },
  { title: '耗时', key: 'duration', width: 100 },
  { title: '结果', key: 'detail' },
];

async function loadStatus(silent = false) {
  if (!silent) loading.value = true;
  try {
    const response = await props.api.post('plugin/TVSeasonRepair/ui_status', {});
    state.value = unwrap(response) || state.value;
    error.value = '';
  } catch (err) {
    error.value = err?.message || '读取状态失败';
  } finally {
    if (!silent) loading.value = false;
  }
}

async function run(path, payload = {}, successText = '') {
  loading.value = true;
  error.value = '';
  message.value = '';
  try {
    const response = await props.api.post(`plugin/TVSeasonRepair/${path}`, payload);
    const body = response?.data ?? response;
    if (body?.success === false) error.value = body.message || '操作失败';
    else message.value = body?.message || successText || '操作已提交';
    await loadStatus(true);
  } catch (err) {
    error.value = err?.message || '操作失败';
  } finally {
    loading.value = false;
  }
}

function openDialog(name, tab = '') {
  dialog.value = name;
  if (tab) recordTab.value = tab;
}

onMounted(() => {
  loadStatus();
  timer = window.setInterval(() => loadStatus(true), 10000);
});
onUnmounted(() => window.clearInterval(timer));

return (_ctx, _cache) => {
  const _component_VProgressLinear = _resolveComponent("VProgressLinear");
  const _component_VAlert = _resolveComponent("VAlert");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
  const _component_VTextField = _resolveComponent("VTextField");
  const _component_VDataTable = _resolveComponent("VDataTable");
  const _component_VTab = _resolveComponent("VTab");
  const _component_VTabs = _resolveComponent("VTabs");
  const _component_VWindowItem = _resolveComponent("VWindowItem");
  const _component_VWindow = _resolveComponent("VWindow");
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
      _createVNode(_component_VCard, {
        class: "dash-card card-scan",
        onClick: _cache[0] || (_cache[0] = $event => (openDialog('scan')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[13] || (_cache[13] = _createElementVNode("div", { class: "card-label" }, "扫描候选", -1)),
              _createElementVNode("div", _hoisted_3, _toDisplayString(summary.value.candidate_count || 0), 1),
              _createElementVNode("div", _hoisted_4, "可安全修复 " + _toDisplayString(summary.value.safe_count || 0) + " 部", 1),
              _createVNode(_component_VIcon, {
                class: "card-arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "dash-card card-active",
        onClick: _cache[1] || (_cache[1] = $event => (openDialog('active')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[14] || (_cache[14] = _createElementVNode("div", { class: "card-label" }, "处理中", -1)),
              _createElementVNode("div", _hoisted_5, _toDisplayString(summary.value.active_count || 0), 1),
              _cache[15] || (_cache[15] = _createElementVNode("div", { class: "card-note" }, "查看队列与实时状态", -1)),
              _createVNode(_component_VIcon, {
                class: "card-arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "dash-card card-result",
        onClick: _cache[2] || (_cache[2] = $event => (openDialog('records', 'success')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[16] || (_cache[16] = _createElementVNode("div", { class: "card-label" }, "修复结果", -1)),
              _createElementVNode("div", _hoisted_6, _toDisplayString(summary.value.success_count || 0), 1),
              _createElementVNode("div", _hoisted_7, "失败 " + _toDisplayString(summary.value.failed_count || 0) + " 条", 1),
              _createVNode(_component_VIcon, {
                class: "card-arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      }),
      _createVNode(_component_VCard, {
        class: "dash-card card-log",
        onClick: _cache[3] || (_cache[3] = $event => (openDialog('records', 'scan')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[17] || (_cache[17] = _createElementVNode("div", { class: "card-label" }, "任务记录", -1)),
              _createElementVNode("div", _hoisted_8, _toDisplayString(summary.value.log_count || 0), 1),
              _createElementVNode("div", _hoisted_9, "可回滚 " + _toDisplayString(summary.value.rollback_count || 0) + " 条", 1),
              _createVNode(_component_VIcon, {
                class: "card-arrow",
                icon: "mdi-chevron-right"
              })
            ]),
            _: 1
          })
        ]),
        _: 1
      })
    ]),
    _createElementVNode("div", _hoisted_10, [
      _createVNode(_component_VBtn, {
        class: "action-primary",
        "prepend-icon": "mdi-magnify",
        onClick: _cache[4] || (_cache[4] = $event => (run('scan')))
      }, {
        default: _withCtx(() => [...(_cache[18] || (_cache[18] = [
          _createTextVNode("扫描媒体库", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        class: "action-info",
        "prepend-icon": "mdi-eye-outline",
        onClick: _cache[5] || (_cache[5] = $event => (run('batch', { execute: false })))
      }, {
        default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
          _createTextVNode("预览安全项目", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        class: "action-warning",
        "prepend-icon": "mdi-tools",
        onClick: _cache[6] || (_cache[6] = $event => (run('batch', { execute: true })))
      }, {
        default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
          _createTextVNode("批量修复", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        class: "action-log",
        "prepend-icon": "mdi-text-box-outline",
        onClick: _cache[7] || (_cache[7] = $event => (openDialog('records', 'scan')))
      }, {
        default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
          _createTextVNode("查看任务记录", -1)
        ]))]),
        _: 1
      })
    ]),
    _createVNode(_component_VAlert, {
      type: "info",
      variant: "tonal",
      class: "headline"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(state.value.headline), 1)
      ]),
      _: 1
    }),
    _createVNode(_component_VDialog, {
      modelValue: dialogOpen.value,
      "onUpdate:modelValue": _cache[12] || (_cache[12] = $event => ((dialogOpen).value = $event)),
      "max-width": "1240",
      scrollable: ""
    }, {
      default: _withCtx(() => [
        _createVNode(_component_VCard, { class: "dialog-card" }, {
          default: _withCtx(() => [
            _createVNode(_component_VCardTitle, { class: "dialog-title" }, {
              default: _withCtx(() => [
                _createElementVNode("span", null, _toDisplayString(dialog.value === 'scan' ? '扫描结果' : dialog.value === 'active' ? '处理任务' : '任务记录'), 1),
                _createVNode(_component_VBtn, {
                  icon: "mdi-close",
                  variant: "text",
                  onClick: _cache[8] || (_cache[8] = $event => (dialog.value = ''))
                })
              ]),
              _: 1
            }),
            _createVNode(_component_VDivider),
            (dialog.value === 'scan')
              ? (_openBlock(), _createBlock(_component_VCardText, {
                  key: 0,
                  class: "dialog-body"
                }, {
                  default: _withCtx(() => [
                    _createVNode(_component_VAlert, {
                      type: "info",
                      variant: "tonal",
                      class: "mb-3"
                    }, {
                      default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                        _createTextVNode("只有连续、无重复并且总集数严格等于 TMDB 正式季度合计的项目才允许自动修复。", -1)
                      ]))]),
                      _: 1
                    }),
                    _createVNode(_component_VTextField, {
                      modelValue: scanSearch.value,
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((scanSearch).value = $event)),
                      "prepend-inner-icon": "mdi-magnify",
                      label: "搜索媒体",
                      variant: "outlined",
                      density: "comfortable",
                      "hide-details": "",
                      class: "mb-3"
                    }, null, 8, ["modelValue"]),
                    _createVNode(_component_VDataTable, {
                      headers: scanHeaders,
                      items: state.value.scan_results,
                      search: scanSearch.value,
                      "items-per-page": 20,
                      class: "data-table"
                    }, {
                      "item.status": _withCtx(({ item }) => [
                        _createElementVNode("span", {
                          class: _normalizeClass(item.safe ? 'status-safe' : 'status-manual')
                        }, _toDisplayString(item.safe ? '可安全修复' : '人工核对'), 3)
                      ]),
                      "item.actions": _withCtx(({ item }) => [
                        (item.safe)
                          ? (_openBlock(), _createElementBlock("div", _hoisted_11, [
                              _createVNode(_component_VBtn, {
                                size: "small",
                                class: "table-preview",
                                onClick: $event => (run('apply', { series_rel: item.series_rel, execute: false }))
                              }, {
                                default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
                                  _createTextVNode("预览", -1)
                                ]))]),
                                _: 1
                              }, 8, ["onClick"]),
                              _createVNode(_component_VBtn, {
                                size: "small",
                                class: "table-fix",
                                onClick: $event => (run('apply', { series_rel: item.series_rel, execute: true }))
                              }, {
                                default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
                                  _createTextVNode("修复", -1)
                                ]))]),
                                _: 1
                              }, 8, ["onClick"])
                            ]))
                          : (_openBlock(), _createElementBlock("span", {
                              key: 1,
                              class: "reason-text",
                              title: item.reason
                            }, _toDisplayString(item.reason), 9, _hoisted_12))
                      ]),
                      _: 1
                    }, 8, ["items", "search"])
                  ]),
                  _: 1
                }))
              : (dialog.value === 'active')
                ? (_openBlock(), _createBlock(_component_VCardText, {
                    key: 1,
                    class: "dialog-body"
                  }, {
                    default: _withCtx(() => [
                      _createVNode(_component_VDataTable, {
                        headers: jobHeaders,
                        items: state.value.active_jobs,
                        "items-per-page": 20,
                        class: "data-table"
                      }, {
                        "item.started_at": _withCtx(({ item }) => [
                          _createTextVNode(_toDisplayString(item.started_at || item.created_at || '—'), 1)
                        ]),
                        "item.finished_at": _withCtx(() => [...(_cache[25] || (_cache[25] = [
                          _createTextVNode("—", -1)
                        ]))]),
                        "item.duration": _withCtx(() => [...(_cache[26] || (_cache[26] = [
                          _createTextVNode("运行中", -1)
                        ]))]),
                        "no-data": _withCtx(() => [...(_cache[27] || (_cache[27] = [
                          _createElementVNode("div", { class: "empty" }, "当前没有处理中的任务", -1)
                        ]))]),
                        _: 1
                      }, 8, ["items"])
                    ]),
                    _: 1
                  }))
                : (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                    _createVNode(_component_VTabs, {
                      modelValue: recordTab.value,
                      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((recordTab).value = $event)),
                      class: "record-tabs",
                      "show-arrows": ""
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VTab, { value: "scan" }, {
                          default: _withCtx(() => [...(_cache[28] || (_cache[28] = [
                            _createTextVNode("扫描日志", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "success" }, {
                          default: _withCtx(() => [...(_cache[29] || (_cache[29] = [
                            _createTextVNode("成功记录", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "failed" }, {
                          default: _withCtx(() => [...(_cache[30] || (_cache[30] = [
                            _createTextVNode("失败记录", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "operation" }, {
                          default: _withCtx(() => [...(_cache[31] || (_cache[31] = [
                            _createTextVNode("预览与回滚", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "rollback" }, {
                          default: _withCtx(() => [...(_cache[32] || (_cache[32] = [
                            _createTextVNode("最近修复", -1)
                          ]))]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }, 8, ["modelValue"]),
                    _createVNode(_component_VDivider),
                    _createVNode(_component_VWindow, {
                      modelValue: recordTab.value,
                      "onUpdate:modelValue": _cache[11] || (_cache[11] = $event => ((recordTab).value = $event)),
                      class: "record-window"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VWindowItem, { value: "scan" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_13, [
                              _createVNode(_component_VDataTable, {
                                headers: operationHeaders,
                                items: state.value.scan_logs,
                                "items-per-page": 20,
                                class: "data-table"
                              }, {
                                "item.duration": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(formatDuration(item)), 1)
                                ]),
                                "no-data": _withCtx(() => [...(_cache[33] || (_cache[33] = [
                                  _createElementVNode("div", { class: "empty" }, "暂无扫描日志", -1)
                                ]))]),
                                _: 1
                              }, 8, ["items"])
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VWindowItem, { value: "success" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_14, [
                              _createVNode(_component_VDataTable, {
                                headers: jobHeaders,
                                items: state.value.success_jobs,
                                "items-per-page": 20,
                                class: "data-table"
                              }, {
                                "item.started_at": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(item.started_at || item.created_at), 1)
                                ]),
                                "item.finished_at": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(item.finished_at || item.updated_at), 1)
                                ]),
                                "item.duration": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(formatDuration(item)), 1)
                                ]),
                                "no-data": _withCtx(() => [...(_cache[34] || (_cache[34] = [
                                  _createElementVNode("div", { class: "empty" }, "暂无成功记录", -1)
                                ]))]),
                                _: 1
                              }, 8, ["items"])
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VWindowItem, { value: "failed" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_15, [
                              _createVNode(_component_VDataTable, {
                                headers: jobHeaders,
                                items: state.value.failed_jobs,
                                "items-per-page": 20,
                                class: "data-table"
                              }, {
                                "item.started_at": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(item.started_at || item.created_at), 1)
                                ]),
                                "item.finished_at": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(item.finished_at || item.updated_at), 1)
                                ]),
                                "item.duration": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(formatDuration(item)), 1)
                                ]),
                                "no-data": _withCtx(() => [...(_cache[35] || (_cache[35] = [
                                  _createElementVNode("div", { class: "empty" }, "暂无失败记录", -1)
                                ]))]),
                                _: 1
                              }, 8, ["items"])
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VWindowItem, { value: "operation" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_16, [
                              _createVNode(_component_VDataTable, {
                                headers: operationHeaders,
                                items: state.value.other_logs,
                                "items-per-page": 20,
                                class: "data-table"
                              }, {
                                "item.duration": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(formatDuration(item)), 1)
                                ]),
                                "no-data": _withCtx(() => [...(_cache[36] || (_cache[36] = [
                                  _createElementVNode("div", { class: "empty" }, "暂无预览或回滚日志", -1)
                                ]))]),
                                _: 1
                              }, 8, ["items"])
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VWindowItem, { value: "rollback" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_17, [
                              _createVNode(_component_VDataTable, {
                                headers: [{ title: '媒体', key: 'name' }, { title: '完成时间', key: 'finished_at', width: 200 }, { title: '动作号', key: 'action_id', width: 260 }, { title: '操作', key: 'actions', sortable: false, width: 100 }],
                                items: state.value.actions,
                                "items-per-page": 20,
                                class: "data-table"
                              }, {
                                "item.finished_at": _withCtx(({ item }) => [
                                  _createTextVNode(_toDisplayString(item.finished_at || '旧记录'), 1)
                                ]),
                                "item.actions": _withCtx(({ item }) => [
                                  _createVNode(_component_VBtn, {
                                    size: "small",
                                    class: "table-undo",
                                    onClick: $event => (run('undo', { action_id: item.action_id }))
                                  }, {
                                    default: _withCtx(() => [...(_cache[37] || (_cache[37] = [
                                      _createTextVNode("回滚", -1)
                                    ]))]),
                                    _: 1
                                  }, 8, ["onClick"])
                                ]),
                                "no-data": _withCtx(() => [...(_cache[38] || (_cache[38] = [
                                  _createElementVNode("div", { class: "empty" }, "暂无可回滚记录", -1)
                                ]))]),
                                _: 1
                              }, 8, ["items"])
                            ])
                          ]),
                          _: 1
                        })
                      ]),
                      _: 1
                    }, 8, ["modelValue"])
                  ], 64))
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-648c5245"]]);

export { Page as default };
