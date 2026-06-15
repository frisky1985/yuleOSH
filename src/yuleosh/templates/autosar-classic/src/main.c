/*
 * AUTOSAR Classic Platform Application
 */

#include "Rte_App.h"
#include "Os.h"

int main(void)
{
    EcuM_Init();
    SchM_Init();
    Com_Init();
    StartOS(OSDEFAULTAPPMODE);
    return 0;
}

TASK(AppTask_10ms)
{
    SchM_App_10ms();
    TerminateTask();
}

TASK(AppTask_100ms)
{
    SchM_App_100ms();
    TerminateTask();
}
