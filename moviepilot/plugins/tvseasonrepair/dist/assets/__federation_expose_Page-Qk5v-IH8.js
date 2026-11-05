import { importShared } from './__federation_fn_import-JrT3xvdd.js';

const _export_sfc = (sfc, props) => {
  const target = sfc.__vccOpts || sfc;
  for (const [key, val] of props) {
    target[key] = val;
  }
  return target;
};

const {resolveComponent:_resolveComponent,openBlock:_openBlock,createBlock:_createBlock,createCommentVNode:_createCommentVNode,toDisplayString:_toDisplayString,createTextVNode:_createTextVNode,withCtx:_withCtx,createVNode:_createVNode,createElementVNode:_createElementVNode,createElementBlock:_createElementBlock,renderList:_renderList,Fragment:_Fragment} = await importShared('vue');


const _hoisted_1 = { class: "season-page" };
const _hoisted_2 = { class: "actions mb-4" };
const _hoisted_3 = { class: "dashboard-grid" };
const _hoisted_4 = { class: "card-value" };
const _hoisted_5 = { class: "card-note" };
const _hoisted_6 = { class: "card-value" };
const _hoisted_7 = { class: "card-value" };
const _hoisted_8 = { class: "card-note" };
const _hoisted_9 = { class: "card-value" };
const _hoisted_10 = { class: "card-note" };
const _hoisted_11 = {
  key: 0,
  class: "empty"
};
const _hoisted_12 = { class: "item-title" };
const _hoisted_13 = { class: "item-meta" };
const _hoisted_14 = { class: "item-meta" };
const _hoisted_15 = { class: "item-result" };
const _hoisted_16 = {
  key: 0,
  class: "item-actions"
};
const _hoisted_17 = {
  key: 0,
  class: "empty"
};
const _hoisted_18 = { class: "item-title" };
const _hoisted_19 = { class: "item-meta" };
const _hoisted_20 = { class: "item-result" };
const _hoisted_21 = { class: "dialog-body" };
const _hoisted_22 = {
  key: 0,
  class: "empty"
};
const _hoisted_23 = { class: "item-title" };
const _hoisted_24 = { class: "item-meta" };
const _hoisted_25 = { class: "item-result" };
const _hoisted_26 = { class: "dialog-body" };
const _hoisted_27 = {
  key: 0,
  class: "empty"
};
const _hoisted_28 = { class: "item-title" };
const _hoisted_29 = { class: "item-meta" };
const _hoisted_30 = { class: "item-result" };
const _hoisted_31 = { class: "dialog-body" };
const _hoisted_32 = {
  key: 0,
  class: "empty"
};
const _hoisted_33 = { class: "item-title" };
const _hoisted_34 = { class: "item-meta" };
const _hoisted_35 = { class: "item-result" };
const _hoisted_36 = { class: "dialog-body" };
const _hoisted_37 = {
  key: 0,
  class: "empty"
};
const _hoisted_38 = { class: "item-title" };
const _hoisted_39 = { class: "item-meta" };
const _hoisted_40 = { class: "item-result" };
const _hoisted_41 = { class: "dialog-body" };
const _hoisted_42 = {
  key: 0,
  class: "empty"
};
const _hoisted_43 = { class: "item-title" };
const _hoisted_44 = { class: "item-meta" };

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
  const _component_VBtn = _resolveComponent("VBtn");
  const _component_VIcon = _resolveComponent("VIcon");
  const _component_VCardText = _resolveComponent("VCardText");
  const _component_VCard = _resolveComponent("VCard");
  const _component_VCardTitle = _resolveComponent("VCardTitle");
  const _component_VDivider = _resolveComponent("VDivider");
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
    _createVNode(_component_VAlert, {
      type: "info",
      variant: "tonal",
      class: "mb-4 headline"
    }, {
      default: _withCtx(() => [
        _createTextVNode(_toDisplayString(state.value.headline), 1)
      ]),
      _: 1
    }),
    _createElementVNode("div", _hoisted_2, [
      _createVNode(_component_VBtn, {
        variant: "flat",
        color: "primary",
        "prepend-icon": "mdi-magnify",
        onClick: _cache[0] || (_cache[0] = $event => (run('scan')))
      }, {
        default: _withCtx(() => [...(_cache[11] || (_cache[11] = [
          _createTextVNode("扫描媒体库", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        variant: "outlined",
        "prepend-icon": "mdi-eye-outline",
        onClick: _cache[1] || (_cache[1] = $event => (run('batch', { execute: false })))
      }, {
        default: _withCtx(() => [...(_cache[12] || (_cache[12] = [
          _createTextVNode("预览安全项目", -1)
        ]))]),
        _: 1
      }),
      _createVNode(_component_VBtn, {
        variant: "outlined",
        "prepend-icon": "mdi-tools",
        onClick: _cache[2] || (_cache[2] = $event => (run('batch', { execute: true })))
      }, {
        default: _withCtx(() => [...(_cache[13] || (_cache[13] = [
          _createTextVNode("批量修复", -1)
        ]))]),
        _: 1
      })
    ]),
    _createElementVNode("div", _hoisted_3, [
      _createVNode(_component_VCard, {
        class: "dash-card card-scan",
        variant: "outlined",
        onClick: _cache[3] || (_cache[3] = $event => (openDialog('scan')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[14] || (_cache[14] = _createElementVNode("div", { class: "card-label" }, "扫描候选", -1)),
              _createElementVNode("div", _hoisted_4, _toDisplayString(summary.value.candidate_count || 0), 1),
              _createElementVNode("div", _hoisted_5, "可安全修复 " + _toDisplayString(summary.value.safe_count || 0) + " 部", 1),
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
        variant: "outlined",
        onClick: _cache[4] || (_cache[4] = $event => (openDialog('active')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[15] || (_cache[15] = _createElementVNode("div", { class: "card-label" }, "处理中", -1)),
              _createElementVNode("div", _hoisted_6, _toDisplayString(summary.value.active_count || 0), 1),
              _cache[16] || (_cache[16] = _createElementVNode("div", { class: "card-note" }, "查看队列与实时状态", -1)),
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
        variant: "outlined",
        onClick: _cache[5] || (_cache[5] = $event => (openDialog('records', 'success')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[17] || (_cache[17] = _createElementVNode("div", { class: "card-label" }, "修复结果", -1)),
              _createElementVNode("div", _hoisted_7, _toDisplayString(summary.value.success_count || 0), 1),
              _createElementVNode("div", _hoisted_8, "失败 " + _toDisplayString(summary.value.failed_count || 0) + " 条", 1),
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
        variant: "outlined",
        onClick: _cache[6] || (_cache[6] = $event => (openDialog('records', 'scan')))
      }, {
        default: _withCtx(() => [
          _createVNode(_component_VCardText, null, {
            default: _withCtx(() => [
              _cache[18] || (_cache[18] = _createElementVNode("div", { class: "card-label" }, "任务记录", -1)),
              _createElementVNode("div", _hoisted_9, _toDisplayString(summary.value.log_count || 0), 1),
              _createElementVNode("div", _hoisted_10, "可回滚 " + _toDisplayString(summary.value.rollback_count || 0) + " 条", 1),
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
    _createVNode(_component_VDialog, {
      modelValue: dialogOpen.value,
      "onUpdate:modelValue": _cache[10] || (_cache[10] = $event => ((dialogOpen).value = $event)),
      "max-width": "1080",
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
                  onClick: _cache[7] || (_cache[7] = $event => (dialog.value = ''))
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
                    (!state.value.scan_results.length)
                      ? (_openBlock(), _createElementBlock("div", _hoisted_11, "暂无候选项目"))
                      : _createCommentVNode("", true),
                    (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(state.value.scan_results, (item) => {
                      return (_openBlock(), _createBlock(_component_VCard, {
                        key: item.series_rel,
                        variant: "outlined",
                        class: "list-card"
                      }, {
                        default: _withCtx(() => [
                          _createVNode(_component_VCardText, null, {
                            default: _withCtx(() => [
                              _createElementVNode("div", _hoisted_12, _toDisplayString(item.name), 1),
                              _createElementVNode("div", _hoisted_13, "当前：" + _toDisplayString(item.current_summary), 1),
                              _createElementVNode("div", _hoisted_14, "TMDB：" + _toDisplayString(item.official_summary), 1),
                              _createElementVNode("div", _hoisted_15, _toDisplayString(item.safe ? '可安全修复' : `需人工核对：${item.reason}`), 1),
                              (item.safe)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_16, [
                                    _createVNode(_component_VBtn, {
                                      size: "small",
                                      variant: "outlined",
                                      onClick: $event => (run('apply', { series_rel: item.series_rel, execute: false }))
                                    }, {
                                      default: _withCtx(() => [...(_cache[19] || (_cache[19] = [
                                        _createTextVNode("预览", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["onClick"]),
                                    _createVNode(_component_VBtn, {
                                      size: "small",
                                      variant: "flat",
                                      color: "primary",
                                      onClick: $event => (run('apply', { series_rel: item.series_rel, execute: true }))
                                    }, {
                                      default: _withCtx(() => [...(_cache[20] || (_cache[20] = [
                                        _createTextVNode("确认修复", -1)
                                      ]))]),
                                      _: 1
                                    }, 8, ["onClick"])
                                  ]))
                                : _createCommentVNode("", true)
                            ]),
                            _: 2
                          }, 1024)
                        ]),
                        _: 2
                      }, 1024))
                    }), 128))
                  ]),
                  _: 1
                }))
              : (dialog.value === 'active')
                ? (_openBlock(), _createBlock(_component_VCardText, {
                    key: 1,
                    class: "dialog-body"
                  }, {
                    default: _withCtx(() => [
                      (!state.value.active_jobs.length)
                        ? (_openBlock(), _createElementBlock("div", _hoisted_17, "当前没有处理中的任务"))
                        : _createCommentVNode("", true),
                      (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(state.value.active_jobs, (job) => {
                        return (_openBlock(), _createBlock(_component_VCard, {
                          key: job.id,
                          variant: "outlined",
                          class: "list-card"
                        }, {
                          default: _withCtx(() => [
                            _createVNode(_component_VCardText, null, {
                              default: _withCtx(() => [
                                _createElementVNode("div", _hoisted_18, _toDisplayString(job.name), 1),
                                _createElementVNode("div", _hoisted_19, "开始：" + _toDisplayString(job.started_at || job.created_at || '—'), 1),
                                _createElementVNode("div", _hoisted_20, _toDisplayString(job.message), 1)
                              ]),
                              _: 2
                            }, 1024)
                          ]),
                          _: 2
                        }, 1024))
                      }), 128))
                    ]),
                    _: 1
                  }))
                : (_openBlock(), _createElementBlock(_Fragment, { key: 2 }, [
                    _createVNode(_component_VTabs, {
                      modelValue: recordTab.value,
                      "onUpdate:modelValue": _cache[8] || (_cache[8] = $event => ((recordTab).value = $event)),
                      class: "record-tabs",
                      "show-arrows": ""
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VTab, { value: "scan" }, {
                          default: _withCtx(() => [...(_cache[21] || (_cache[21] = [
                            _createTextVNode("扫描日志", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "success" }, {
                          default: _withCtx(() => [...(_cache[22] || (_cache[22] = [
                            _createTextVNode("成功记录", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "failed" }, {
                          default: _withCtx(() => [...(_cache[23] || (_cache[23] = [
                            _createTextVNode("失败记录", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "operation" }, {
                          default: _withCtx(() => [...(_cache[24] || (_cache[24] = [
                            _createTextVNode("预览与回滚", -1)
                          ]))]),
                          _: 1
                        }),
                        _createVNode(_component_VTab, { value: "rollback" }, {
                          default: _withCtx(() => [...(_cache[25] || (_cache[25] = [
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
                      "onUpdate:modelValue": _cache[9] || (_cache[9] = $event => ((recordTab).value = $event)),
                      class: "record-window"
                    }, {
                      default: _withCtx(() => [
                        _createVNode(_component_VWindowItem, { value: "scan" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_21, [
                              (!state.value.scan_logs.length)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_22, "暂无扫描日志"))
                                : _createCommentVNode("", true),
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(state.value.scan_logs, (row) => {
                                return (_openBlock(), _createBlock(_component_VCard, {
                                  key: row.id,
                                  variant: "outlined",
                                  class: "list-card"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VCardText, null, {
                                      default: _withCtx(() => [
                                        _createElementVNode("div", _hoisted_23, _toDisplayString(row.title) + " · " + _toDisplayString(row.status === 'success' ? '成功' : '失败'), 1),
                                        _createElementVNode("div", _hoisted_24, "开始 " + _toDisplayString(row.started_at) + "　结束 " + _toDisplayString(row.finished_at || '—') + "　耗时 " + _toDisplayString(formatDuration(row)), 1),
                                        _createElementVNode("div", _hoisted_25, _toDisplayString(row.detail), 1)
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024))
                              }), 128))
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VWindowItem, { value: "success" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_26, [
                              (!state.value.success_jobs.length)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_27, "暂无成功记录"))
                                : _createCommentVNode("", true),
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(state.value.success_jobs, (row) => {
                                return (_openBlock(), _createBlock(_component_VCard, {
                                  key: row.id,
                                  variant: "outlined",
                                  class: "list-card"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VCardText, null, {
                                      default: _withCtx(() => [
                                        _createElementVNode("div", _hoisted_28, _toDisplayString(row.name), 1),
                                        _createElementVNode("div", _hoisted_29, "开始 " + _toDisplayString(row.started_at || row.created_at) + "　结束 " + _toDisplayString(row.finished_at || row.updated_at) + "　耗时 " + _toDisplayString(formatDuration(row)), 1),
                                        _createElementVNode("div", _hoisted_30, _toDisplayString(row.message), 1)
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024))
                              }), 128))
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VWindowItem, { value: "failed" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_31, [
                              (!state.value.failed_jobs.length)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_32, "暂无失败记录"))
                                : _createCommentVNode("", true),
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(state.value.failed_jobs, (row) => {
                                return (_openBlock(), _createBlock(_component_VCard, {
                                  key: row.id,
                                  variant: "outlined",
                                  class: "list-card"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VCardText, null, {
                                      default: _withCtx(() => [
                                        _createElementVNode("div", _hoisted_33, _toDisplayString(row.name), 1),
                                        _createElementVNode("div", _hoisted_34, "开始 " + _toDisplayString(row.started_at || row.created_at) + "　结束 " + _toDisplayString(row.finished_at || row.updated_at) + "　耗时 " + _toDisplayString(formatDuration(row)), 1),
                                        _createElementVNode("div", _hoisted_35, _toDisplayString(row.message), 1)
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024))
                              }), 128))
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VWindowItem, { value: "operation" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_36, [
                              (!state.value.other_logs.length)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_37, "暂无预览或回滚日志"))
                                : _createCommentVNode("", true),
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(state.value.other_logs, (row) => {
                                return (_openBlock(), _createBlock(_component_VCard, {
                                  key: row.id,
                                  variant: "outlined",
                                  class: "list-card"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VCardText, null, {
                                      default: _withCtx(() => [
                                        _createElementVNode("div", _hoisted_38, _toDisplayString(row.title) + " · " + _toDisplayString(row.status), 1),
                                        _createElementVNode("div", _hoisted_39, "开始 " + _toDisplayString(row.started_at) + "　结束 " + _toDisplayString(row.finished_at || '—') + "　耗时 " + _toDisplayString(formatDuration(row)), 1),
                                        _createElementVNode("div", _hoisted_40, _toDisplayString(row.detail), 1)
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024))
                              }), 128))
                            ])
                          ]),
                          _: 1
                        }),
                        _createVNode(_component_VWindowItem, { value: "rollback" }, {
                          default: _withCtx(() => [
                            _createElementVNode("div", _hoisted_41, [
                              (!state.value.actions.length)
                                ? (_openBlock(), _createElementBlock("div", _hoisted_42, "暂无可回滚记录"))
                                : _createCommentVNode("", true),
                              (_openBlock(true), _createElementBlock(_Fragment, null, _renderList(state.value.actions, (row) => {
                                return (_openBlock(), _createBlock(_component_VCard, {
                                  key: row.action_id,
                                  variant: "outlined",
                                  class: "list-card"
                                }, {
                                  default: _withCtx(() => [
                                    _createVNode(_component_VCardText, { class: "rollback-row" }, {
                                      default: _withCtx(() => [
                                        _createElementVNode("div", null, [
                                          _createElementVNode("div", _hoisted_43, _toDisplayString(row.name), 1),
                                          _createElementVNode("div", _hoisted_44, _toDisplayString(row.finished_at || '旧记录未保存完成时间') + " · " + _toDisplayString(row.action_id), 1)
                                        ]),
                                        _createVNode(_component_VBtn, {
                                          size: "small",
                                          variant: "outlined",
                                          onClick: $event => (run('undo', { action_id: row.action_id }))
                                        }, {
                                          default: _withCtx(() => [...(_cache[26] || (_cache[26] = [
                                            _createTextVNode("回滚", -1)
                                          ]))]),
                                          _: 1
                                        }, 8, ["onClick"])
                                      ]),
                                      _: 2
                                    }, 1024)
                                  ]),
                                  _: 2
                                }, 1024))
                              }), 128))
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
const Page = /*#__PURE__*/_export_sfc(_sfc_main, [['__scopeId',"data-v-f6131e5e"]]);

export { Page as default };
