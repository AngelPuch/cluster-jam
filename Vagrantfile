Vagrant.configure("2") do |config|
    config.vm.box = "bento/ubuntu-24.04"
    config.vm.box_version = "202510.26.0"
    config.vm.hostname = "cluster-jam"
    config.vm.boot_timeout = 600

    config.vm.network "private_network", ip: "192.168.56.17"

    config.vm.network "forwarded_port", guest: 443, host: 8443,
    host_ip: "127.0.0.1", auto_correct: false
    config.vm.network "public_network", ip: "192.168.1.77"

    config.vm.synced_folder ".", "/vagrant", disabled: true

    config.vm.provider "virtualbox" do |vb|
        vb.name = "cluster-jam"
        vb.memory = 4096
        vb.cpus = 2
    end

    config.vm.provision "shell",
        path: "script-provision.sh",
        privileged: true,
        env: { "DOCKER_USER" => "vagrant" }
end

