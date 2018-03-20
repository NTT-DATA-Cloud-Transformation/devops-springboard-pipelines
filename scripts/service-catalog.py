#!/usr/bin/env python

from botocore.credentials import RefreshableCredentials
from botocore.session import get_session
from boto3 import Session
import argparse
import random
import os
import fnmatch
import datetime, time


def put_template_in_s3(client_s3,new_template_path):
    ntp=new_template_path
    new_template_path = PORTFOLIO_NAME+ "/" + new_template_path.split("/",1)[1]
    filename_without_ext=new_template_path.split(".")[0]
    print "path for putting--------------{}".format(filename_without_ext + "-git-hash-" +os.environ['CODEBUILD_SOURCE_VERSION']+".yml")
    response = client_s3.put_object( Body=open(ntp),Bucket=BUCKET_NAME,Key=filename_without_ext + "-git-hash-" +os.environ['CODEBUILD_SOURCE_VERSION']+".yml")
    print "new template with version {} uploaded to bucket".format(response['VersionId'])
    upload_path = filename_without_ext + "-git-hash-" +os.environ['CODEBUILD_SOURCE_VERSION']+".yml"
    return (response['VersionId'],upload_path)

def parse_arguments():
    parser = argparse.ArgumentParser(description='Product Creation/Updation')
    parser.add_argument('--role_arn', '-ra', help='Role Arn used for accessing AWS resources', required=True)
    parser.add_argument('--support_email', '-se', help='Support email for the service catalog products and portfolio', required=True)
    parser.add_argument('--bucket_name', '-bn', help='Bucket name for storing templates for products of service catalog', required=True)
    parser.add_argument('--bucket_path', '-bp', help='S3 bucket folder path for storing templates for products of service catalog like workshop/ecs-workshop', required=True)
    parser.add_argument('--portfolio_name', '-pn', help='Potfolio name under to which products are associated', required=True)
    parser.add_argument('--support_url', '-su', help='Support Url with http/https  like https://www.flux7.com ', required=True)
    args = parser.parse_args()
    return args


def assumed_temp_session(role_arn,session_name):
    session = Session()
    def refresh():
        credentials = session.client('sts').assume_role(RoleArn=role_arn,RoleSessionName=session_name)['Credentials']
        return dict(
            access_key=credentials['AccessKeyId'],
            secret_key=credentials['SecretAccessKey'],
            token=credentials['SessionToken'],
            # Silly that we basically stringify so it can be parsed again
            expiry_time=credentials['Expiration'].isoformat())

    session_credentials = RefreshableCredentials.create_from_metadata(metadata=refresh(),refresh_using=refresh,method='sts-assume-role')
    s = get_session()
    s._credentials = session_credentials
    region = session._session.get_config_variable('region') or 'us-east-1'
    s.set_config_variable('region', region)
    return (Session(botocore_session=s),region)

def create_connection():
    if ROLE_ARN:
        session = assumed_temp_session(ROLE_ARN, "{0}-{1}".format(ROLE_ARN.split("/")[1],random.randrange(0, 99999999)))[0]
        region= assumed_temp_session(ROLE_ARN, "{0}-{1}".format(ROLE_ARN.split("/")[1],random.randrange(0, 99999999)))[1]
        client = session.client('servicecatalog',region_name=region)
        client_s3 = session.client('s3',region_name=region)
    return (client,region,client_s3)



def create_product(client,product_name,temp_s3_url):
    print "creating product"
    print temp_s3_url
    print VERSION
    response = client.create_product(Name=product_name,Owner="flux7",Description="ecs-wrokshop",Distributor="flux7",SupportDescription="to enhance the code pipeline to use the service catalog",
        SupportEmail=SUPPORT_EMAIL,
        SupportUrl=SUPPORT_URL,
        ProductType='CLOUD_FORMATION_TEMPLATE',
        ProvisioningArtifactParameters={
            'Name': VERSION,
            'Description': 'initial version',
            'Info': {
                'LoadTemplateFromURL': temp_s3_url
            },
            'Type':'CLOUD_FORMATION_TEMPLATE'
        },
        #IdempotencyToken=product_name
    )
    if  response['ProductViewDetail']['Status'] == 'CREATED':
        print "product creation successful "


    product_id = response['ProductViewDetail']['ProductViewSummary']['ProductId']
    product_version_id = response['ProvisioningArtifactDetail']['Id']
    product_version_name = response['ProvisioningArtifactDetail']['Name']
    return (product_id,product_version_id,product_version_name)


def create_version_of_product(client,version,temp_s3_url,product_id,product_name,region,client_s3):
    print "version=",version
    url ="{}/{}/".format(client_s3.meta.endpoint_url,BUCKET_NAME) + temp_s3_url
    #end_point_of_template= "-git-hash-" + os.environ['CODEBUILD_SOURCE_VERSION']+".yml"
    #main_url= temp_s3_url.split(".yml")[0]
    print "URL=",url
    response = client.create_provisioning_artifact(ProductId=product_id,
        Parameters={
            'Name': version,
            'Info': {
                'LoadTemplateFromURL': url
            },
            'Type':'CLOUD_FORMATION_TEMPLATE'
        },
        #IdempotencyToken=version
    )

    print "new version  {} created for product {} in region {}".format(version,product_name,region)




def create_portfolio(client,portfolio_name,region):
    response = client.create_portfolio(
        DisplayName=portfolio_name,
        Description="for the ecs-workshop",
        ProviderName="flux7",
        #IdempotencyToken=portfolio_name
    )
    portfolio_id= response['PortfolioDetail']['Id']
    print "portfolio {} created in region {}".format(portfolio_name,region)
    return portfolio_id

def attach_product_to_portfolio(client,product_id,portfolio_id):
    response = client.associate_product_with_portfolio(
        ProductId=product_id,
        PortfolioId=portfolio_id,
    )

def associate_role_with_portfolio(client,portfolio_id):
    response = client.associate_principal_with_portfolio(
        PortfolioId=portfolio_id,
        PrincipalARN=ROLE_ARN,
        PrincipalType='IAM'
    )
    print "role arn {} is associated with portfolio {}".format(ROLE_ARN,portfolio_id)

def compare_templates(conn,template_url,product_name,product_template):
    client_s3 = conn[2]
    object_info_list=template_url.split("/",4)
    bucket=object_info_list[3]
    key=object_info_list[4].split(".yml")[0]+".yml"
    print bucket
    print key
    with open('temp_template.yml', 'wb') as data:
        client_s3.download_fileobj(bucket,key, data)

    old_template_path = 'temp_template.yml'
    new_template_path = '../cf-templates/{}/{}'.format(product_name,product_template)
    diff_set=set()
    with open(new_template_path) as f1, open(old_template_path) as f2:
        difference = set(f1).difference(f2)

    print difference
    if difference == diff_set:
        print False,old_template_path
        return (False,old_template_path)
    else:
        print True,new_template_path
        return (True,new_template_path)

def get_latest_version_template(ser_cat_clt_conn,latest_version_id,product_id):
    response = ser_cat_clt_conn.describe_provisioning_artifact(ProvisioningArtifactId=latest_version_id,ProductId=product_id)
    print "latest template = {}".format(response['Info']['TemplateUrl'])
    return response['Info']['TemplateUrl']



def portfolio(ser_cat_clt_conn,region):
    """To create portfolio
    """
    portfolio_dict = ser_cat_clt_conn.list_portfolios(PageSize=20)
    if portfolio_dict['PortfolioDetails']==[]:
        print "creating portfolio {} in region {}".format(PORTFOLIO_NAME,region)
        portfolio_id = create_portfolio(ser_cat_clt_conn,PORTFOLIO_NAME,region)
    elif portfolio_dict['PortfolioDetails'] != []:
        for  portfolio in portfolio_dict['PortfolioDetails']:
            if portfolio['DisplayName']==PORTFOLIO_NAME:
                print "portfolio {} already exist in region {}".format(PORTFOLIO_NAME,region)
                portfolio_id = portfolio['Id']
                break
        else:
            print "creating portfolio {} in region {}".format(PORTFOLIO_NAME,region)
            portfolio_id = create_portfolio(ser_cat_clt_conn,PORTFOLIO_NAME,region)

    return portfolio_id

def main(temp_s3_url,product_name,conn,product_template,portfolio_id):
    ser_cat_clt_conn = conn[0]
    region = conn[1]
    client_s3 = conn[2]

    """TO create product
    """
    response = ser_cat_clt_conn.search_products()
    for product in response['ProductViewSummaries']:
        if product['Name'] == product_name:
            product_id =  product['ProductId']
            version_response = ser_cat_clt_conn.describe_product(Id=product_id)
            tdict= {}
            vdict= {}
            for version in  version_response['ProvisioningArtifacts']:
                tdict[time.mktime(version['CreatedTime'].timetuple())]=version['Id']
                vdict[time.mktime(version['CreatedTime'].timetuple())]=version['Name']

            latest_version_id= tdict[max(tdict.keys())]
            latest_version_name= vdict[max(vdict.keys())]
            print latest_version_id
            print latest_version_name
            template_latest = get_latest_version_template(ser_cat_clt_conn,latest_version_id,product_id)
            print "product_template=",product_template

            comp_status = compare_templates(conn,template_latest,product_name,product_template)

            # create version of product if template changed
            if comp_status[0] == True:
                global VERSION
                VERSION = "v"+str(float(latest_version_name.split("v")[1])+.1)
                print VERSION
                # upload new template to bucket for new version
                template_info = put_template_in_s3(client_s3,comp_status[1])
                create_version_of_product(ser_cat_clt_conn,VERSION,template_info[1],product_id,product_name,region,client_s3)

            break

            """
            for version in version_response['ProvisioningArtifacts']:
                if "v1.0.0" == version['Name']:
                    print "product {} with version {}   already exist in region {} and attached with portfolio {}".format(product_name,"v1.0.0",region,PORTFOLIO_NAME)
                    break
            else:
                #To create New  Version of  existing product
                create_version_of_product(ser_cat_clt_conn,"v1.0.0",ARGS.version_desc,temp_s3_url,product_id,product_name,region)
            break
            """

    else:
        product_id,product_version_id,product_version_name =create_product(ser_cat_clt_conn,product_name,temp_s3_url)
        print "product {} created in region {} with version {}".format(product_name,region,product_version_name)
        #TO associate the product with portfolio
        attach_product_to_portfolio(ser_cat_clt_conn,product_id,portfolio_id)
        print "product {} attached with portfolio {}".format(product_name,PORTFOLIO_NAME)




if __name__ == "__main__":
    ARGS = parse_arguments()
    SUPPORT_EMAIL = ARGS.support_email
    BUCKET_NAME = ARGS.bucket_name
    BUCKET_PATH = ARGS.bucket_path
    PORTFOLIO_NAME = ARGS.portfolio_name
    product_name_list=os.listdir('../cf-templates')
    #product_name_list= ["common","custombuild"]
    print product_name_list
    ROLE_ARN = ARGS.role_arn
    SUPPORT_URL = ARGS.support_url

    conn = create_connection()
    ser_cat_clt_conn = conn[0]
    region = conn[1]
    client_s3 = conn[2]

    portfolio_id = portfolio(ser_cat_clt_conn,region)
    # attach role with portfolio
    associate_role_with_portfolio(ser_cat_clt_conn,portfolio_id)

    for product_name in product_name_list:
        VERSION = "v1.0"
        product_template=fnmatch.filter(os.listdir('../cf-templates/{}'.format(product_name)), '*.yml')[0]
        product_temp_s3_url='{}/{}/{}'.format(client_s3.meta.endpoint_url,BUCKET_NAME,"{}/cf-templates/{}/{}".format(BUCKET_PATH,product_name,product_template))
        print "product_name={}".format(product_name)
        print "product template name={}/{}\n".format(product_name,product_template)
        main(product_temp_s3_url,product_name,conn,product_template,portfolio_id)


