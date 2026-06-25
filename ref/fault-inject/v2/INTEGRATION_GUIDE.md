/*******************************************************************************
 * A66-T Per-Task Fault Injection — Integration Guide
 * ========================================================================
 *
 * This guide shows how to wire the TaskFaultInject module into the existing
 * A66-T SBM codebase. All changes are guarded by A66T_TASK_FAULT_INJECT_ENABLE
 * and compile to nothing when STD_OFF.
 *
 * Integration Checklist:
 *   [ ] Step 1: Add TaskFaultInject.c to the build (IAR project or CMake)
 *   [ ] Step 2: One-time init call in main.c
 *   [ ] Step 3: Register each task + add TASK_FAULT_CHECK() to its loop
 *   [ ] Step 4: Add TASK_FAULT_IS_ACTIVE() checks to error paths
 *   [ ] Step 5: (Optional) Wire UDS DID 0xF193 for remote trigger
 ******************************************************************************/

/*===========================================================================
 * Step 1: Build Integration
 *=========================================================================*/
/*
 * IAR EWARM:
 *   1. Add inc/TaskFaultInject.h and inc/TaskFaultInject_Cfg.h to header includes
 *   2. Add src/TaskFaultInject.c to the project sources
 *   3. Ensure FreeRTOS include path is accessible
 *   4. Set A66T_TASK_FAULT_INJECT_ENABLE = STD_ON in TaskFaultInject_Cfg.h
 *
 * CMake:
 *   target_sources(app PRIVATE
 *       ${BSW_DIR}/FaultInject/src/TaskFaultInject.c
 *   )
 */

/*===========================================================================
 * Step 2: Initialization in main.c
 *=========================================================================*/
/*
 * Add after the scheduler starts (e.g., at the end of Rtos_InitTask or
 * at the start of SchedTask_Init):
 *
 *   #if (A66T_TASK_FAULT_INJECT_ENABLE == STD_ON)
 *   TaskFault_Init();
 *   #endif
 *
 * Recommended placement — in Rtos_InitTask(), right before Rte_Start():
 *
 * static void Rtos_InitTask(void *params)
 * {
 *     Rte_Init();
 *     SchedTask_Init();
 *     Rtos_Say_Hello();
 *
 *     #if (A66T_TASK_FAULT_INJECT_ENABLE == STD_ON)
 *     TaskFault_Init();
 *     #endif
 *
 *     Rte_Start();
 *     ...
 * }
 */

/*===========================================================================
 * Step 3: Task Registration Pattern
 *=========================================================================*/
/*
 * Each task that supports fault injection must:
 *   a) Register itself (once, at task start)
 *   b) Add TASK_FAULT_CHECK() at the top of its loop
 *   c) Add TASK_FAULT_END_CHECK() at the end of its loop iteration
 *
 * --- PATTERN A: Simple cyclic task (RteTask_High / RteTask_Low) ---
 *
 * void RteTask_High(void *pvParameters)
 * {
 *     (void)pvParameters;
 *
 *     // Register for fault injection (one-time)
 *     #if (A66T_TASK_FAULT_INJECT_ENABLE == STD_ON)
 *     TaskFault_RegisterTask(xTaskGetCurrentTaskHandle(), "RteHigh");
 *     #endif
 *
 *     WdgM_TaskCheckAlive(WdgM_RteH_Task);
 *
 *     for (;;)
 *     {
 *         TASK_FAULT_CHECK();   // <-- ADD THIS (compiles to nothing if disabled)
 *
 *         osDelayUntil(RTE_TASK_CALL_CYCLE_MS);
 *         RteHCyclic_Func();
 *         WdgM_TaskCheckAlive(WdgM_RteH_Task);
 *
 *         TASK_FAULT_END_CHECK(); // <-- ADD THIS
 *     }
 * }
 *
 * --- PATTERN B: Task with multiple runnables (SchedTask functions) ---
 *
 * Each SchedTask handler runs in the RteHigh context. Insert fault-aware
 * checks into specific runnables, not the scheduler itself.
 *
 * Example — DKI_Main() with fault-injection awareness:
 *
 * void DKI_Main(void)
 * {
 *     // Normal init / handle retrieval
 *     void *dkiHandle = DKI_GetHandle();
 *
 *     // --- Fault injection: simulate NULL handle ---
 *     if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_NULL_HANDLE))
 *     {
 *         dkiHandle = NULL;   // Force NULL to test error path
 *     }
 *
 *     if (NULL == dkiHandle)
 *     {
 *         TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
 *         // ... error handling ...
 *         return;
 *     }
 *
 *     // --- Fault injection: simulate invalid parameter ---
 *     uint32_t param = getParam();
 *     if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_INVALID_PARAM))
 *     {
 *         param = 0xFFFFFFFF;  // Force invalid param
 *     }
 *
 *     DKF_RESULT_E ret = DKI_Process(dkiHandle, param);
 *     if (ret == DKF_RESULT_ERR_PARAM)
 *     {
 *         TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
 *         return;
 *     }
 *
 *     // Normal path continues...
 * }
 *
 * --- PATTERN C: Renamed injection — VEHICLE context ---
 *
 * void Vehicle_Main(void)
 * {
 *     S_VEHICLE_HANDLE *handle = Vehicle_GetHandle();
 *
 *     if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_NULL_HANDLE))
 *     {
 *         handle = NULL;
 *     }
 *
 *     if (NULL == handle)
 *     {
 *         TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
 *         return;
 *     }
 *
 *     // --- Timeout simulation ---
 *     if (TASK_FAULT_IS_ACTIVE(TASK_FAULT_SIM_TIMEOUT))
 *     {
 *         // Simulate: CAN message not received
 *         Vehicle_EnterFailSafeMode();
 *         TASK_FAULT_REPORT(TASK_FAULT_RESULT_PASSED);
 *         return;
 *     }
 *
 *     Vehicle_ProcessCANMessages(handle);
 * }
 */

/*===========================================================================
 * Step 4: UDS Trigger (Optional)
 *=========================================================================*/
/*
 * Wire the new DID 0xF193 into Desc_Ingeek.c's WriteDataByIdentifier handler:
 *
 *   case 0xF193:   // A66T_TASK_FAULT_INJECT_UDS_DID
 *   {
 *       TaskHandle_t targetTask;
 *       TaskFault_Type_E faultType;
 *
 *       // Byte 0-3: fault type (uint32, little-endian)
 *       // Byte 4-7: task index (uint32, little-endian)
 *       //   task index: 0=RteHigh, 1=RteLow, 2=Rtos_Init
 *
 *       if (dataLength < 8U)
 *       {
 *           nrc = NRC_INCORRECT_MESSAGE_LENGTH;
 *           break;
 *       }
 *
 *       faultType  = (TaskFault_Type_E)UDS_ReadU32(&data[0]);
 *       taskIdx    = UDS_ReadU32(&data[4]);
 *
 *       targetTask = TaskFault_GetHandleByIndex(taskIdx);
 *       if (targetTask == NULL)
 *       {
 *           nrc = NRC_REQUEST_OUT_OF_RANGE;
 *           break;
 *       }
 *
 *       if (TaskFault_Inject(targetTask, faultType))
 *       {
 *           // Return DID + fault type as positive response
 *           UDS_SendPositiveResponse();
 *       }
 *       else
 *       {
 *           nrc = NRC_CONDITIONS_NOT_CORRECT;
 *       }
 *       break;
 *   }
 */

/*===========================================================================
 * Step 5: Python Test Runner (Optional)
 *=========================================================================*/
/*
 * Extend the existing A66-T_fault_inject_test_runner.py with task-level tests:
 *
 * TASK_FAULT_TESTS = [
 *     {"id": 1, "task_idx": 0, "task_name": "RteHigh",
 *      "fault": "NullHandle", "inject_val": 0x01,
 *      "expected_result": "PASSED"},
 *     {"id": 2, "task_idx": 0, "task_name": "RteHigh",
 *      "fault": "InvalidParam", "inject_val": 0x02,
 *      "expected_result": "PASSED"},
 *     {"id": 3, "task_idx": 0, "task_name": "RteHigh",
 *      "fault": "Timeout", "inject_val": 0x03,
 *      "expected_result": "PASSED"},
 *     # ... etc for each task
 * ]
 *
 * def run_task_fault_test(tc):
 *     # Send UDS $2E F193 with task_idx and fault_type
 *     data = struct.pack("<II", tc["inject_val"], tc["task_idx"])
 *     send_uds_write(0xF193, data)
 *
 *     # Wait for task to respond (does NOT reset the ECU!)
 *     time.sleep(2.0)
 *
 *     # Read result via UDS $22 F192 (new DID for reading task fault results)
 *     result = read_task_fault_result()
 *     assert result["status"] == tc["expected_result"]
 */

/*===========================================================================
 * Recommended Task Injection Priority Order
 *=========================================================================*/
/*
 * Inject faults in this order to systematically verify error handling:
 *
 * 1. DKI_Main          — critical DKF path, NULL handle is HIGH risk
 * 2. Vehicle_Main       — VehAuth, VehCtrl, cloud commands
 * 3. SE_MainCycle       — HSM/secure element communication
 * 4. LocationApi        — UWB/BLE localization
 * 5. BleCom_MainFunction — BLE link management
 * 6. CanTask_Main       — CAN stack fault recovery (bus-off, timeout)
 * 7. FactoryLine_App    — factory line diagnostics
 * 8. AppMsg_Main        — inter-task messaging reliability
 *
 * Each injection takes ~2 seconds (no reset needed!), so a full suite
 * of 8 tasks × 4 fault types = 32 tests takes approximately 64 seconds.
 */
