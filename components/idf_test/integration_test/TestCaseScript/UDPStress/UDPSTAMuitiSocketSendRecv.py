from TCAction import TCActionBase
from NativeLog import NativeLog
import time
import random
import string


class TestCase(TCActionBase.CommonTCActionBase):
    def __init__(self, test_case, test_env, timeout=45, log_path=TCActionBase.LOG_PATH):
        TCActionBase.CommonTCActionBase.__init__(self, test_case, test_env, timeout=timeout, log_path=log_path)
        # load param from excel
        cmd_set = test_case["cmd set"]
        for i in range(1, len(cmd_set)):
            if cmd_set[i][0] != "dummy":
                cmd_string = "self." + cmd_set[i][0]
                exec cmd_string
        self.result_cntx = TCActionBase.ResultCheckContext(self, test_env, self.tc_name)
        pass

    def execute(self):
        TCActionBase.TCActionBase.execute(self)
        self.result_cntx.start()

        try:
            # configurable params
            send_len = self.send_len
            test_time = self.test_time * 60
            server_echo = self.server_echo
            conn_number = self.conn_number
            sta_number = self.sta_number
            send_delay = self.send_delay
            # configurable params
        except StandardError, e:
            NativeLog.add_trace_critical("Error configuration for TCPTransparent script, error is %s" % e)
            raise StandardError("Error configuration")

        # step0 reboot
        for i in range(sta_number + 1):
            checker_stings = ["P SSC%d C !!!ready!!!" % (i + 1)]
            test_action_string = ["SSCC SSC%d reboot" % (i + 1)]
            fail_string = "Fail, Fail to reboot"
            if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string) is False:
                return

        # turn off recv print
        for i in range(sta_number + 1):
            checker_stings = ["P SSC%d C +RECVPRINT:0" % (i + 1)]
            test_action_string = ["SSCC SSC%d soc -R -o 0" % (i + 1)]
            fail_string = "Fail, Fail to turn off recv print"
            if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string) is False:
                return

        # step1, set softAP mode on SSC1
        checker_stings = ["R SSC1 C +MODE:OK"]
        test_action_string = ["SSCC SSC1 op -S -o 2"]
        fail_string = "Fail, Fail to set mode on SSC1"
        if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string) is False:
            return

        # step2, set STA mode on SSC2-SSCn
        for i in range(sta_number):
            checker_stings = ["R SSC%d C +MODE:OK" % (i + 2)]
            test_action_string = ["SSCC SSC%d op -S -o 1" % (i + 2)]
            fail_string = "Fail, Fail to set mode on SSC%d" % (i + 2)
            if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string) is False:
                return

        # step3, set ssid/password on SSC1
        ssid = "".join([random.choice(string.lowercase) for m in range(10)])
        password = "".join([random.choice(string.lowercase) for m in range(10)])

        checker_stings = ["R SSC1 C +SAP:OK"]
        test_action_string = ["SSCC SSC1 ap -S -s %s -p %s -n 10 -t 0 -m 8" % (ssid, password)]
        fail_string = "Fail, Fail to set ssid/password on SSC1"
        if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string) is False:
            return

        # step4, all STA join SSC1(soft AP)
        for i in range(sta_number):
            checker_stings = ["R SSC%d C +JAP:CONNECTED,%s" % (i + 2, ssid)]
            test_action_string = ["SSCC SSC%d ap -C -s %s -p %s" % (i + 2, ssid, password)]
            fail_string = "Fail, Fail to connect to SSC1"
            if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string, check_time=450) is False:
                return

        # step5, get all the STA ip
        for i in range(sta_number):
            checker_stings = ["R SSC%d A <SSC%d_IP>:\+STAIP:192.168.4.(\d+)" % (i + 2, i + 2)]
            test_action_string = ["SSCC SSC%d ip -Q" % (i + 2)]
            fail_string = "Fail, Fail to get SSC%d ip" % (i + 2)
            if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string) is False:
                return
            else:
                print "SSC%d ip is:" % (i + 2), self.get_parameter("SSC%d_IP" % (i + 2))

        udp_port_list = []
        # step6, create multi UDP socket on all targets
        for i in range(conn_number):

            udp_port = random.randint(10000, 20000)
            udp_port_list.append(udp_port)

            checker_stings = ["R SSC2 A <SSC2_sock%d>:\+BIND:(\d+),OK" % i]
            test_action_string = ["SSCC SSC2 soc -B -t UDP -p %s" % udp_port]
            fail_string = "Fail, SSC2 Fail to bind"
            if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string) is False:
                return

            checker_stings = ["R SSC3 A <SSC3_sock%d>:\+BIND:(\d+),OK" % i]
            test_action_string = ["SSCC SSC3 soc -B -t UDP -p %s" % (udp_port + 1)]
            fail_string = "Fail, SSC3 Fail to bind"
            if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string) is False:
                return

        start_time = time.time()
        # step7, do send/recv, SSC2<---->other STAs
        while time.time() - start_time < test_time:
            # drop off the delay time if it's greater than 20ms
            if send_delay > 20:
                send_delay -= 10

            checker_stings = []
            test_action_string = []
            if server_echo is True:

                # SSC2 send packets to SSC3
                ssc3_ip = "192.168.4." + self.get_parameter("SSC3_IP")
                for i in range(conn_number):
                    test_action_string.append("SSC SSC2 soc -S -s <SSC2_sock%s> -i %s -p %s -l %d -n 1000 -j %d" % (
                        i, ssc3_ip, udp_port_list[i] + 1, send_len, send_delay))
                    checker_stings.append("P SSC2 RE \+SEND:\d+,OK NC CLOSED NC ERROR")

            # SSC3 send packets to SSC2
            ssc2_ip = "192.168.4." + self.get_parameter("SSC2_IP")
            for i in range(conn_number):
                test_action_string.append("SSC SSC3 soc -S -s <SSC3_sock%d> -i %s  -p %s -l %d -n 1000 -j %d" % (
                    i, ssc2_ip, udp_port_list[i], send_len, send_delay))
                checker_stings.append("P SSC3 RE \+SEND:\d+,OK NC CLOSED NC ERROR")

            fail_string = "Fail, Failed to send/recv data"
            if self.load_and_exe_one_step(checker_stings, test_action_string, fail_string,
                                          check_freq=1, check_time=300) is False:
                break

        NativeLog.add_trace_critical("time escape: %s" % (time.time() - start_time))
        if (time.time() - start_time) >= test_time:
            self.result_cntx.set_result("Succeed")
        else:
            self.result_cntx.set_result("Failed")

            # finally, execute done

    def result_check(self, port_name, data):
        TCActionBase.CommonTCActionBase.result_check(self, port_name, data)
        self.result_cntx.append_data(port_name, data)


def main():
    pass


if __name__ == '__main__':
    main()
